"""HVE がメインPhaseと敵対的レビューPhaseの所有権を分離する契約。"""
from __future__ import annotations

import ast
import inspect
import textwrap

import pytest

from hve import runner as runner_module


_REVIEW_SUFFIX_FUNCTION = "_build_review_ownership_suffix"


def _review_suffix(auto_contents_review: bool) -> str:
    builder = getattr(runner_module, _REVIEW_SUFFIX_FUNCTION, None)
    assert callable(builder), (
        f"hve.runner.{_REVIEW_SUFFIX_FUNCTION} is required to make review "
        "ownership explicit in the final main-task prompt"
    )
    return builder(auto_contents_review)


def test_review_suffix_disables_subagents_when_hve_review_is_off() -> None:
    suffix = _review_suffix(False)
    assert suffix.startswith("\n\n")
    assert "1回のインライン・セルフチェック" in suffix
    assert "Review Sub-agentを起動しない" in suffix
    assert "敵対的レビューを実施しない" in suffix
    assert "Phase 3" not in suffix


def test_review_suffix_delegates_to_phase3_when_hve_review_is_on() -> None:
    suffix = _review_suffix(True)
    assert suffix.startswith("\n\n")
    assert "メインタスク内ではReview Sub-agentを起動しない" in suffix
    assert "HVE Phase 3" in suffix
    assert "敵対的レビュー" in suffix
    assert "1回のインライン・セルフチェック" not in suffix


def _run_step_ast() -> ast.AsyncFunctionDef:
    tree = ast.parse(textwrap.dedent(inspect.getsource(runner_module.StepRunner.run_step)))
    function = tree.body[0]
    assert isinstance(function, ast.AsyncFunctionDef)
    return function


def _call_name(call: ast.Call) -> str:
    if isinstance(call.func, ast.Name):
        return call.func.id
    if isinstance(call.func, ast.Attribute):
        return call.func.attr
    return ""


def _statement_list_containing(
    root: ast.AST,
    target: ast.stmt,
) -> list[ast.stmt] | None:
    for _field_name, value in ast.iter_fields(root):
        if isinstance(value, list) and target in value:
            return value
        if isinstance(value, ast.AST):
            found = _statement_list_containing(value, target)
            if found is not None:
                return found
        elif isinstance(value, list):
            for item in value:
                if isinstance(item, ast.AST):
                    found = _statement_list_containing(item, target)
                    if found is not None:
                        return found
    return None


def test_main_prompt_appends_review_ownership_once_and_sends_result() -> None:
    """既存booleanで作ったsuffixを1回だけ最終Promptへ連結して送信する。"""
    function = _run_step_ast()
    review_assignments: list[ast.Assign] = []
    send_assignments: list[ast.Assign] = []

    for node in ast.walk(function):
        if (
            isinstance(node, ast.Assign)
            and isinstance(node.value, ast.BinOp)
            and isinstance(node.value.right, ast.Call)
            and isinstance(node.value.right.func, ast.Name)
            and node.value.right.func.id == _REVIEW_SUFFIX_FUNCTION
        ):
                review_assignments.append(node)
        if (
            isinstance(node, ast.Assign)
            and len(node.targets) == 1
            and isinstance(node.targets[0], ast.Name)
            and node.targets[0].id == "main_response"
            and isinstance(node.value, ast.Await)
            and isinstance(node.value.value, ast.Call)
            and _call_name(node.value.value)
            == "_send_and_wait_with_model_call_failure_guard"
        ):
            send_assignments.append(node)

    assert len(review_assignments) == 1
    assignment = review_assignments[0]
    assert len(assignment.targets) == 1
    target = assignment.targets[0]
    assert isinstance(target, ast.Name) and target.id == "_injected_prompt"
    assert isinstance(assignment.value, ast.BinOp)
    assert isinstance(assignment.value.op, ast.Add)
    assert isinstance(assignment.value.left, ast.Name)
    assert assignment.value.left.id == "_injected_prompt"
    assert isinstance(assignment.value.right, ast.Call)
    review_call = assignment.value.right
    assert isinstance(review_call.func, ast.Name)
    assert review_call.func.id == _REVIEW_SUFFIX_FUNCTION
    assert len(review_call.args) == 1
    assert review_call.keywords == []
    assert ast.dump(review_call.args[0], include_attributes=False) == ast.dump(
        ast.Attribute(
            value=ast.Attribute(
                value=ast.Name(id="self", ctx=ast.Load()),
                attr="config",
                ctx=ast.Load(),
            ),
            attr="auto_contents_review",
            ctx=ast.Load(),
        ),
        include_attributes=False,
    )

    assert len(send_assignments) == 1
    send_assignment = send_assignments[0]
    assert isinstance(send_assignment.value, ast.Await)
    send_call = send_assignment.value.value
    assert isinstance(send_call, ast.Call)
    assert len(send_call.args) >= 2
    sent_prompt = send_call.args[1]
    assert isinstance(sent_prompt, ast.Name) and sent_prompt.id == "_injected_prompt"

    review_body = _statement_list_containing(function, assignment)
    send_body = _statement_list_containing(function, send_assignment)
    assert review_body is not None
    assert review_body is send_body
    assert review_body.index(assignment) < review_body.index(send_assignment)


def test_review_suffix_has_no_new_runtime_switch_or_sdk_tool_policy() -> None:
    """helperは既存booleanだけを受け取る。"""
    builder = getattr(runner_module, _REVIEW_SUFFIX_FUNCTION, None)
    assert callable(builder)
    signature = inspect.signature(builder)
    assert list(signature.parameters) == ["auto_contents_review"]


def _is_auto_contents_review(expression: ast.AST) -> bool:
    return (
        isinstance(expression, ast.Attribute)
        and expression.attr == "auto_contents_review"
        and isinstance(expression.value, ast.Attribute)
        and expression.value.attr == "config"
        and isinstance(expression.value.value, ast.Name)
        and expression.value.value.id == "self"
    )


def test_phase3_send_rechecks_and_phase_count_are_guarded_and_bounded() -> None:
    """Phase 3は既存boolean配下だけで実行し、再確認は最大2回に固定する。"""
    function = _run_step_ast()
    guarded_ifs = [
        node
        for node in ast.walk(function)
        if isinstance(node, ast.If) and _is_auto_contents_review(node.test)
    ]

    phase3_guards: list[ast.If] = []
    phase_count_guards: list[ast.If] = []
    for guarded_if in guarded_ifs:
        guarded_body = ast.Module(body=guarded_if.body, type_ignores=[])
        assigned_names = {
            target.id
            for node in ast.walk(guarded_body)
            if isinstance(node, ast.Assign)
            for target in node.targets
            if isinstance(target, ast.Name)
        }
        if "review_response" in assigned_names:
            phase3_guards.append(guarded_if)
        if any(
            isinstance(node, ast.AugAssign)
            and isinstance(node.target, ast.Name)
            and node.target.id == "total_phases"
            and isinstance(node.op, ast.Add)
            and isinstance(node.value, ast.Constant)
            and node.value.value == 1
            for node in ast.walk(guarded_body)
        ):
            phase_count_guards.append(guarded_if)

    assert len(phase3_guards) == 1
    assert len(phase_count_guards) == 1

    phase3_body = ast.Module(body=phase3_guards[0].body, type_ignores=[])
    sends_by_target: dict[str, list[ast.Assign]] = {
        "review_response": [],
        "recheck_response": [],
    }
    for node in ast.walk(phase3_body):
        if not (
            isinstance(node, ast.Assign)
            and len(node.targets) == 1
            and isinstance(node.targets[0], ast.Name)
            and node.targets[0].id in sends_by_target
            and isinstance(node.value, ast.Await)
            and isinstance(node.value.value, ast.Call)
            and _call_name(node.value.value) == "send_and_wait"
        ):
            continue
        sends_by_target[node.targets[0].id].append(node)

    assert len(sends_by_target["review_response"]) == 1
    assert len(sends_by_target["recheck_response"]) == 1

    bounded_recheck_loops = [
        node
        for node in ast.walk(phase3_body)
        if (
            isinstance(node, ast.For)
            and isinstance(node.target, ast.Name)
            and node.target.id == "cycle"
            and isinstance(node.iter, ast.Call)
            and isinstance(node.iter.func, ast.Name)
            and node.iter.func.id == "range"
            and [
                arg.value
                for arg in node.iter.args
                if isinstance(arg, ast.Constant)
            ]
            == [1, 3]
        )
    ]
    assert len(bounded_recheck_loops) == 1


@pytest.mark.parametrize("enabled", [False, True])
def test_review_suffix_is_deterministic(enabled: bool) -> None:
    assert _review_suffix(enabled) == _review_suffix(enabled)
