"""生成スクリプトの必須変数ガードが launcher の供給契約と一致することを固定する。

live canary（run `20260728T034239-836daa` の再開実行）が Step 1.3 の prep stage で
`DATA_DEPLOY_IDENTITY_CLIENT_ID: parameter null or not set` により停止した。

prep stage は managed identity `data-deploy-identity` を **自分で作成する**stage で
あり、その clientId は Azure が採番するため prep 実行前には存在しない。
[hve/asdw_data_runtime_context.py](hve/asdw_data_runtime_context.py) の docstring と
要求定義 `FR-WF-ASDW-03` はいずれも「prep 成功後に launcher が読み戻す」と明記し、
`_build_child_environment` も `stage != "prep"` のときだけ供給する。
にもかかわらず生成器の prep テンプレートだけが当該キーを必須ガードとして宣言して
いたため、鶏と卵の矛盾で prep が起動直後に落ちていた。

個別の 1 行ではなく「各 stage のガードは launcher がその stage へ供給できるキーの
部分集合である」という不変条件を固定し、同種の欠陥の再発を防ぐ。
"""

from __future__ import annotations

import re
import sys
from pathlib import Path
from unittest import mock

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from hve import asdw_data_script_launcher as launcher  # noqa: E402
from hve import runner as runner_module  # noqa: E402
from hve.asdw_data_runtime_context import (  # noqa: E402
    build_asdw_data_deploy_bootstrap_context,
)
from hve.workflow_registry import get_workflow  # noqa: E402

_REPO_ROOT = Path(__file__).resolve().parents[2]
_SUBSCRIPTION_ID = "00000000-0000-0000-0000-000000000001"
_GUARD_PATTERN = re.compile(r"\$\{([A-Z0-9_]+):\?\}")

_STAGE_SCRIPT = {
    "prep": launcher._PREP,
    "create": launcher._CREATE,
    "registration": launcher._REGISTRATION,
    "verify": launcher._VERIFY,
}

# execute_stage が _build_child_environment の直後に注入するキー。
# stage ごとに供給元が異なるため、ここで明示して契約を可視化する。
_CALL_SITE_KEYS = {
    "prep": {"HVE_ASDW_SCRIPT_DIR", "HVE_ASDW_SCRIPT_STAGE"},
    "create": {
        "HVE_ASDW_SCRIPT_DIR",
        "HVE_ASDW_SCRIPT_STAGE",
        "HVE_ASDW_SAMPLE_DATA_JSON",
        "DATA_CREATE_RUN_ID",
    },
    "registration": {
        "HVE_ASDW_SCRIPT_DIR",
        "HVE_ASDW_SCRIPT_STAGE",
        "AUDIT_RECORD_JSON",
        "DATA_REGISTER_RUN_ID",
    },
    "verify": {
        "HVE_ASDW_SCRIPT_DIR",
        "HVE_ASDW_SCRIPT_STAGE",
        "DATA_VERIFY_RUN_ID",
    },
}


def _bootstrap_parent_environment() -> dict[str, str]:
    """Step 1.3 が Azure write 前に凍結する実際の親環境を組み立てる。"""
    step = next(s for s in get_workflow("asdw-web").steps if s.id == "1.3")
    params = dict(step.default_params or {})
    params["resource_group"] = "example-rg"
    inputs = {
        context_key: params[param_key]
        for context_key, param_key in (
            runner_module._ASDW_DATA_DEPLOY_BOOTSTRAP_PARAM_KEYS.items()
        )
    }
    context = build_asdw_data_deploy_bootstrap_context(
        workflow_params=params,
        bootstrap_inputs=inputs,
        subscription_id=_SUBSCRIPTION_ID,
    )
    return dict(context)


def _stage_environment(stage: str) -> set[str]:
    parent = _bootstrap_parent_environment()
    with mock.patch.object(
        launcher,
        "_resolve_deploy_identity_client_id",
        return_value="11111111-1111-1111-1111-111111111111",
    ):
        environment = launcher._build_child_environment(parent, stage)
    return set(environment) | _CALL_SITE_KEYS[stage]


@pytest.mark.parametrize("stage", tuple(_STAGE_SCRIPT))
def test_stage_guards_are_satisfied_by_the_launcher_environment(stage: str) -> None:
    """各 stage のスクリプトが要求する変数を launcher が必ず供給できる。"""
    script = (_REPO_ROOT / _STAGE_SCRIPT[stage]).read_text(encoding="utf-8")
    required = set(_GUARD_PATTERN.findall(script))
    supplied = _stage_environment(stage)

    unsatisfiable = sorted(required - supplied)
    assert not unsatisfiable, (
        f"{stage} stage が launcher の供給契約外の変数を必須にしている: "
        f"{unsatisfiable}"
    )


def test_prep_does_not_require_the_post_prep_read_back_key() -> None:
    """prep は自分が作成する identity の clientId を事前要求してはならない。"""
    prep = (_REPO_ROOT / launcher._PREP).read_text(encoding="utf-8")

    assert runner_module._ASDW_DATA_DEPLOY_READ_BACK_KEY not in set(
        _GUARD_PATTERN.findall(prep)
    ), (
        "prep が作成する managed identity の clientId は Azure が prep 実行後に "
        "採番するため、prep の必須ガードにできない（FR-WF-ASDW-03）"
    )


def test_later_stages_still_require_the_read_back_key() -> None:
    """読み戻し後の stage では ACI に渡すため必須のままであること。"""
    create = (_REPO_ROOT / launcher._CREATE).read_text(encoding="utf-8")
    registration = (_REPO_ROOT / launcher._REGISTRATION).read_text(encoding="utf-8")

    for label, text in (("create", create), ("registration", registration)):
        assert runner_module._ASDW_DATA_DEPLOY_READ_BACK_KEY in set(
            _GUARD_PATTERN.findall(text)
        ), f"{label} は読み戻した clientId を必須にすること"
