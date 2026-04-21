"""test_aqod.py — AQOD ワークフローの基本テスト"""

from __future__ import annotations

import importlib.util as _ilu
import os
import sys

_repo_root = os.path.join(os.path.dirname(__file__), "..", "..")
sys.path.insert(0, os.path.abspath(_repo_root))
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from hve.orchestrator import _collect_params_non_interactive
from hve.template_engine import render_template
from hve.workflow_registry import get_workflow


_main_path = os.path.join(os.path.dirname(__file__), "..", "__main__.py")
_spec = _ilu.spec_from_file_location("hve_main_for_aqod", os.path.abspath(_main_path))
_main_mod = _ilu.module_from_spec(_spec)
_spec.loader.exec_module(_main_mod)
_build_parser = _main_mod._build_parser
_build_params = _main_mod._build_params


def test_aqod_workflow_registered():
    wf = get_workflow("aqod")
    assert wf is not None
    assert wf.name == "Original Docs Review"
    assert wf.steps[0].custom_agent == "QA-DocConsistency"


def test_aqod_parser_and_params_defaults():
    args = _build_parser().parse_args(["orchestrate", "--workflow", "aqod"])
    params = _build_params(args)
    assert params["target_scope"] == "original-docs/"
    assert params["depth"] == "standard"
    assert params["focus_areas"] == ""


def test_aqod_non_interactive_defaults():
    wf = get_workflow("aqod")
    params = _collect_params_non_interactive(wf, {"branch": "main"})
    assert params["target_scope"] == "original-docs/"
    assert params["depth"] == "standard"
    assert params["focus_areas"] == ""


def test_aqod_template_render():
    wf = get_workflow("aqod")
    body = render_template(
        "templates/aqod/step-1.md",
        root_issue_num=1,
        params={
            "target_scope": "original-docs/",
            "depth": "lightweight",
            "focus_areas": "データ整合性",
        },
        wf=wf,
    )
    assert "{aqod_target_scope}" not in body
    assert "original-docs/" in body
    assert "lightweight" in body
    assert "データ整合性" in body
