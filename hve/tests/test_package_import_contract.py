"""`hve` パッケージの import 契約テスト。

保証すること:

1. ``import hve`` 時点で重い依存 (cq / copilot SDK 等) を引き込まない。
   これが崩れると ``hve/__main__.py`` の .venv 再 exec ガードが依存解決より
   後になり、.venv 外の Python から起動したときに即 ModuleNotFoundError で死ぬ。
2. 依存欠落の真因を平坦 import フォールバックで握り潰さない。
   （旧実装は ``No module named 'cq'`` を ``No module named 'config'`` にすり替えていた）
"""
from __future__ import annotations

import subprocess
import sys

import pytest

import hve

_HEAVY_MODULES = ("cq", "hve.config", "hve.runner", "hve.prompts", "hve.qa_merger")


def _run_probe(code: str) -> str:
    result = subprocess.run(
        [sys.executable, "-c", code],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    return result.stdout.strip()


def test_import_hve_does_not_pull_heavy_dependencies():
    loaded = _run_probe(
        "import sys, hve;"
        f"print(','.join(m for m in {_HEAVY_MODULES!r} if m in sys.modules))"
    )
    assert loaded == ""


def test_public_attributes_resolve_lazily():
    from hve.config import SDKConfig
    from hve.console import Console
    from hve.runner import StepRunner

    assert hve.SDKConfig is SDKConfig
    assert hve.Console is Console
    assert hve.StepRunner is StepRunner


def test_all_exported_names_are_resolvable():
    for name in hve.__all__:
        assert getattr(hve, name) is not None


def test_unknown_attribute_raises_attribute_error():
    with pytest.raises(AttributeError):
        hve.definitely_not_an_attribute


def test_submodule_import_still_works():
    from hve import workflow_registry

    assert hasattr(workflow_registry, "get_workflow")


def test_missing_dependency_surfaces_real_cause():
    """cq が解決できないとき ``No module named 'cq'`` がそのまま伝播すること。"""
    code = """
import sys


class _Blocker:
    def find_spec(self, name, path=None, target=None):
        if name == 'cq' or name.startswith('cq.'):
            raise ModuleNotFoundError("No module named 'cq'", name='cq')
        return None


sys.meta_path.insert(0, _Blocker())
try:
    import hve.__main__  # noqa: F401
except ModuleNotFoundError as exc:
    print(exc.name)
else:
    print('NO_ERROR')
"""
    assert _run_probe(code) == "cq"
