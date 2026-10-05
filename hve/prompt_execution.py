"""hve.prompt_execution — Prompt 版の実行計画・plan hash・委譲実行（FR-PROMPT-01 / 03 / 04 / 05 / 11）。

本モジュールは Workflow 実行エンジンを持たない。検証済み request と保存済み GUI 設定から
既存 `orchestrate` サブコマンドの argv を組み立て、承認済みの計画だけを子プロセスとして
起動する薄い境界である。
"""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Dict, List, Mapping, Optional, Sequence, Tuple

from .input_aliases import ResolvedAlias, normalize_alias_pairs, validate_aliases
from .prompt_request import PromptRequest
from .step_inputs import (
    StepInputBundle,
    materialize_step_inputs,
    validate_step_input_bundles,
)
from .resume_service import ResumeService, WorkflowDescriptor
from .run_state_store import DurableStateError, RunStateStore
from .runtime_observability import make_instance_id
from .workflow_order import sort_workflows_by_dependencies
from .workflow_registry import default_step_ids, get_workflow

PLAN_SCHEMA_VERSION = 1
_WORKIQ_NOTICE_REASONS = frozenset({"not-configured", "unverified"})

Runner = Callable[..., "subprocess.CompletedProcess[Any]"]


@dataclass(frozen=True)
class WorkflowPlan:
    workflow_id: str
    requested_workflow_id: str
    steps: Tuple[str, ...]
    argv: Tuple[str, ...]
    input_aliases: Tuple[ResolvedAlias, ...]
    step_input_bundles: Tuple[StepInputBundle, ...] = ()
    step_input_manifest: Optional[str] = None


@dataclass(frozen=True)
class ExecutionPlan:
    schema_version: int
    goal: str
    head_commit: str
    workflows: Tuple[WorkflowPlan, ...]
    notices: Tuple[str, ...] = ()
    execution_policy: Optional[Mapping[str, Any]] = None
    resource_groups: Tuple[Tuple[str, str], ...] = ()

    @property
    def sha256(self) -> str:
        return hashlib.sha256(canonical_plan_json(self).encode("utf-8")).hexdigest()


class WorkIQSourceUnavailable(ValueError):
    """Work IQ縮退後にAKMの実効sourceが0件になった。"""


def _args_request_workiq(args: Any) -> bool:
    """1 Workflow分の実効引数がWork IQを要求しているか返す。"""
    if bool(getattr(args, "workiq", False)) or bool(getattr(args, "ard_workiq_enabled", False)):
        return True
    knowledge = getattr(args, "knowledge_sources", None) or ""
    if isinstance(knowledge, str):
        knowledge = knowledge.split(",")
    if any(str(token).strip() == "workiq" for token in knowledge):
        return True
    sources = str(getattr(args, "sources", "") or "")
    return any(token.strip().lower() == "workiq" for token in sources.split(","))


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
    workiq_capability: Any = None,
) -> ExecutionPlan:
    """検証済み request と保存済み設定から決定的な実行計画を組み立てる。"""
    from .gui.orchestrate_args import args_from_settings

    by_id = {w.workflow_id: w for w in request.workflows}
    ordered = sort_workflows_by_dependencies([w.workflow_id for w in request.workflows])

    root = Path(repo_root).resolve()
    raw_work_root = os.environ.get("HVE_WORK_ROOT", "").strip()
    prompt_work_root = root / "work" / "run" / "prompt-plan"
    if raw_work_root:
        configured_work_root = Path(raw_work_root)
        if not configured_work_root.is_absolute():
            configured_work_root = root / configured_work_root
        try:
            configured_work_root.resolve().relative_to(root)
            prompt_work_root = configured_work_root
        except (OSError, ValueError):
            pass

    pending: List[
        Tuple[
            str,
            Any,
            Tuple[ResolvedAlias, ...],
            Any,
            Tuple[StepInputBundle, ...],
            Optional[str],
        ]
    ] = []
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
        step_input_bundles: Tuple[StepInputBundle, ...] = ()
        step_input_manifest: Optional[str] = None
        if wf_request.step_inputs:
            bundles_by_step, manifest = materialize_step_inputs(
                repo_root=root,
                work_root=prompt_work_root,
                workflow_id=workflow_id,
                specs=wf_request.step_inputs,
                input_aliases=tuple(
                    (alias.canonical, alias.actual) for alias in aliases
                ),
            )
            step_input_bundles = tuple(bundles_by_step.values())
            step_input_manifest = manifest.resolve().relative_to(root).as_posix()
            for bundle in step_input_bundles:
                for entry in bundle.entries:
                    args.step_inputs.append(
                        (
                            bundle.step_id,
                            entry.role,
                            entry.canonical,
                            entry.actual,
                        )
                    )
        pending.append(
            (
                workflow_id,
                wf_request,
                aliases,
                args,
                step_input_bundles,
                step_input_manifest,
            )
        )

    requested = [item for item in pending if _args_request_workiq(item[3])]
    notices: Tuple[str, ...] = ()
    if requested:
        from .workiq import (
            disable_workiq_for_run,
            probe_workiq_plugin_capability,
        )

        capability = workiq_capability
        if capability is None:
            first_args = requested[0][3]
            capability = probe_workiq_plugin_capability(
                cli_path=getattr(first_args, "cli_path", None),
                cli_url=getattr(first_args, "cli_url", None),
                working_directory=repo_root,
            )
        if capability.state != "ready":
            affected: List[str] = []
            for workflow_id, _wf_request, _aliases, args, _bundles, _manifest in requested:
                result = disable_workiq_for_run(args)
                if workflow_id == "akm" and result.sources_became_empty:
                    raise WorkIQSourceUnavailable(
                        "Work IQ無効化後にAKMの取り込みsourceが0件になります。"
                    )
                affected.append(workflow_id)
            notices = (
                "<!-- workiq-disabled: workflows="
                + ",".join(sorted(set(affected)))
                + "; reason="
                + (
                    capability.reason_code
                    if capability.reason_code in _WORKIQ_NOTICE_REASONS
                    else "unverified"
                )
                + " -->",
            )

    policy = request.execution_policy
    policy_argv = _execution_policy_argv(policy)
    plans: List[WorkflowPlan] = []
    for workflow_id, wf_request, aliases, args, bundles, manifest in pending:
        plans.append(
            WorkflowPlan(
                workflow_id=workflow_id,
                requested_workflow_id=wf_request.requested_workflow_id,
                steps=wf_request.steps,
                argv=tuple(args.to_argv()) + policy_argv,
                input_aliases=aliases,
                step_input_bundles=bundles,
                step_input_manifest=manifest,
            )
        )

    return ExecutionPlan(
        schema_version=PLAN_SCHEMA_VERSION,
        goal=request.goal,
        head_commit=head_commit,
        workflows=tuple(plans),
        notices=notices,
        execution_policy=policy.to_dict() if policy is not None else None,
        resource_groups=tuple(
            (w.workflow_id, w.params["resource_group"])
            for w in (by_id[wid] for wid in ordered)
            if policy is not None and w.params.get("resource_group")
        ),
    )


def _execution_policy_argv(policy: Any) -> Tuple[str, ...]:
    """FR-PROMPT-13: 宣言された事前承認を子 orchestrate の隠し引数へ写す。"""
    if policy is None:
        return ()
    argv: List[str] = []
    if policy.unattended:
        argv.append("--unattended")
    for operation in policy.pre_approved_operations:
        argv.extend(["--pre-approved-operation", operation])
    if policy.allow_public_exposure:
        argv.append("--allow-public-exposure")
    if policy.budget_note:
        argv.extend(["--budget-note", policy.budget_note])
    return tuple(argv)


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
    workflows = []
    for wp in plan.workflows:
        workflow_payload = {
            "argv": list(wp.argv),
            "input_aliases": [
                {"actual": a.actual, "canonical": a.canonical}
                for a in wp.input_aliases
            ],
            "steps": list(wp.steps),
            "workflow_id": wp.workflow_id,
        }
        if wp.step_input_bundles:
            workflow_payload["step_input_bundles"] = [
                bundle.to_dict() for bundle in wp.step_input_bundles
            ]
        workflows.append(workflow_payload)
    payload: Dict[str, Any] = {
        "goal": plan.goal,
        "head_commit": plan.head_commit,
        "schema_version": plan.schema_version,
        "workflows": workflows,
    }
    # 宣言が無い request の hash を変えないため、宣言がある場合だけ含める。
    if plan.execution_policy is not None:
        payload["execution_policy"] = dict(plan.execution_policy)
    return json.dumps(payload, sort_keys=True, ensure_ascii=False, separators=(",", ":"))


def _declared_output_paths(workflow_id: str, steps: Sequence[str]) -> List[str]:
    """選択済み Step が宣言する `output_paths` を宣言順・重複排除で返す（FR-DOD-03）。

    `steps` が空（既定の選択）の場合は当該 Workflow の全 Step を対象にする。
    値を推測・補完せず、registry の宣言だけを使う。
    """
    workflow = get_workflow(workflow_id)
    # steps 省略時は CLI と同じ registry の既定の選択を使う（FR-WF-ADI-18 v3.33）
    selected = set(steps) or set(default_step_ids(workflow_id))
    paths: List[str] = []
    for step in getattr(workflow, "steps", ()):
        if selected and getattr(step, "id", None) not in selected:
            continue
        for path in getattr(step, "output_paths", None) or ():
            if path not in paths:
                paths.append(path)
    return paths


def format_plan(plan: ExecutionPlan) -> str:
    """利用者へ提示する計画テキストを返す。"""
    lines = [
        "# Prompt 版 実行計画",
        "",
        f"- HEAD: {plan.head_commit}",
        f"- 実行順: {' -> '.join(wp.workflow_id for wp in plan.workflows)}",
        "",
    ]
    if plan.notices:
        lines.extend(plan.notices)
        lines.append("")
    if plan.execution_policy is not None:
        policy = plan.execution_policy
        operations = ", ".join(policy.get("pre_approved_operations") or []) or "(なし)"
        lines.append("## 事前承認の宣言（execution_policy）")
        lines.append(f"- 無人実行: {'はい' if policy.get('unattended') else 'いいえ'}")
        lines.append(f"- 事前承認した操作: {operations}")
        for workflow_id, resource_group in plan.resource_groups:
            lines.append(f"- デプロイ先 resource_group（{workflow_id}）: `{resource_group}`")
        lines.append(
            f"- 外部公開: {'許可' if policy.get('allow_public_exposure') else '許可しない'}"
        )
        if policy.get("budget_note"):
            lines.append(f"- 予算の注記（記録のみ）: {policy['budget_note']}")
        lines.append("")
    for index, wp in enumerate(plan.workflows, start=1):
        lines.append(f"## {index}. {wp.workflow_id}")
        if wp.requested_workflow_id != wp.workflow_id:
            lines.append(f"- request の表記: `{wp.requested_workflow_id}`")
        lines.append(f"- Step: {', '.join(wp.steps) if wp.steps else '(既定の選択)'}")
        for alias in wp.input_aliases:
            lines.append(f"- 入力別名: `{alias.canonical}` → `{alias.actual}`")
        for bundle in wp.step_input_bundles:
            for entry in bundle.entries:
                canonical = f" / canonical=`{entry.canonical}`" if entry.canonical else ""
                lines.append(
                    f"- Step入力: Step.{bundle.step_id} / role=`{entry.role}`"
                    f"{canonical} / actual=`{entry.actual}` / sha256=`{entry.sha256}`"
                )
        lines.append("- argv:")
        lines.append("  ```")
        lines.append("  " + " ".join(wp.argv))
        lines.append("  ```")
        declared = _declared_output_paths(wp.workflow_id, wp.steps)
        if declared:
            lines.append("- 完了条件（宣言 output_paths）:")
            for path in declared:
                lines.append(f"  - `{path}`")
        else:
            lines.append(
                "- 完了条件（宣言 output_paths）: (宣言なし)"
                " ※ fan-out 展開後に確定する成果物は含みません"
            )
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


def _step_inputs_match_approved_plan(
    plan: ExecutionPlan,
    repo_root: "str | Path",
) -> bool:
    """承認済みbundleのpath/digest/alias対応を子process直前に再検証する。"""
    try:
        for workflow in plan.workflows:
            if not workflow.step_input_bundles:
                continue
            validate_step_input_bundles(
                {
                    bundle.step_id: bundle
                    for bundle in workflow.step_input_bundles
                },
                repo_root=repo_root,
                input_aliases=tuple(
                    (alias.canonical, alias.actual)
                    for alias in workflow.input_aliases
                ),
            )
    except (OSError, ValueError):
        return False
    return True


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
    if not _step_inputs_match_approved_plan(
        plan, cwd if cwd is not None else Path.cwd()
    ):
        print(
            "Prompt execution のStep入力が承認済み計画から変化しました。"
            "子プロセスは起動していません。",
            file=sys.stderr,
        )
        return 1
    execute = runner or _default_runner
    durable_identity: Optional[Tuple[str, Tuple[str, ...]]] = None
    if not dry_run and not any(wp.step_input_bundles for wp in plan.workflows):
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
        if cwd is not None and not _step_inputs_match_approved_plan(plan, cwd):
            print(
                "Prompt execution のStep入力が承認済み計画から変化しました。"
                "子プロセスは起動していません。",
                file=sys.stderr,
            )
            return 1
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
