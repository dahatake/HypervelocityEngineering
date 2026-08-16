"""FR-DAG-04: fan-out 展開の基準ルートが作業リポジトリであることの検証。

背景:
  `hve/orchestrator.py` は fan-out 展開の `repo_root` に
  `Path(__file__).resolve().parent.parent`（= HVE パッケージの設置ディレクトリ）を
  渡していた。HVE を対象リポジトリとは別の場所へ設置して実行すると、カタログが
  対象リポジトリに実在しても展開キーが 0 件になり、当該 Step が `fanout-empty` で
  無警告 skip される。

  本リポジトリは HVE 自身を dogfooding するため
  `Path(__file__).resolve().parent.parent == Path.cwd()` が成立し、素の実行では
  症状が出ない。そのため振る舞いテストでは `chdir` で両者を必ず分離する。
"""
from __future__ import annotations

import ast
import asyncio
from pathlib import Path

import pytest

from hve.config import SDKConfig
from hve.orchestrator import run_workflow

_ORCHESTRATOR_SRC_PATH = Path(__file__).resolve().parents[1] / "orchestrator.py"


def _orchestrator_ast() -> tuple[str, ast.Module]:
    source = _ORCHESTRATOR_SRC_PATH.read_text(encoding="utf-8")
    return source, ast.parse(source)


def _segment(source: str, node: ast.AST) -> str:
    return ast.get_source_segment(source, node) or ""


def _calls_named(tree: ast.Module, name: str) -> list[ast.Call]:
    found: list[ast.Call] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id == name:
            found.append(node)
    return found


class TestFanoutRepoRootIsWorkingRepo:
    """FR-DAG-04: 展開の基準ルートは実行プロセスの作業ディレクトリ。"""

    def test_dry_run_expands_fanout_against_cwd(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        """作業ディレクトリの skeleton だけを展開元にすること。

        UC-ID は本リポジトリの `docs/catalog/use-case-skeleton.md` に存在しない値を
        使う。パッケージ設置ディレクトリを基準にしていると、この 2 件は 1 件も
        現れず、代わりに本リポジトリ側の UC が展開される。
        """
        catalog_dir = tmp_path / "docs" / "catalog"
        catalog_dir.mkdir(parents=True)
        (catalog_dir / "use-case-skeleton.md").write_text(
            "# ユースケース骨格\n"
            "\n"
            "| ID | 名称 | 主アクター | 優先度 |\n"
            "|---|---|---|---|\n"
            "| UC-ZZ01 | 会員登録 | 会員 | 高 |\n"
            "| UC-ZZ02 | ポイント付与 | 会員 | 中 |\n",
            encoding="utf-8",
        )
        monkeypatch.chdir(tmp_path)

        result = asyncio.run(
            run_workflow(
                "ard",
                params={"selected_steps": ["4"], "target_business": "テスト業務"},
                config=SDKConfig(dry_run=True, quiet=True),
            )
        )

        children = sorted(s for s in result.get("skipped", []) if s.startswith("3.2/"))
        assert children == ["3.2/UC-ZZ01", "3.2/UC-ZZ02"], (
            "fan-out の展開元が作業ディレクトリ以外を参照しています: " f"{children}"
        )

    def test_expand_workflow_for_dag_is_not_given_the_package_root(self) -> None:
        source, tree = _orchestrator_ast()
        calls = _calls_named(tree, "_expand_workflow_for_dag")
        assert calls, "_expand_workflow_for_dag の呼び出しが見つかりません"
        for call in calls:
            assert len(call.args) >= 3, "_expand_workflow_for_dag の repo_root 引数が見つかりません"
            segment = _segment(source, call.args[2])
            assert "__file__" not in segment, (
                "fan-out 事前展開の repo_root には作業リポジトリのルートを渡してください: " f"{segment}"
            )

    def test_dag_executor_is_not_given_the_package_root(self) -> None:
        source, tree = _orchestrator_ast()
        calls = _calls_named(tree, "DAGExecutor")
        assert calls, "DAGExecutor の呼び出しが見つかりません"
        checked = 0
        for call in calls:
            for keyword in call.keywords:
                if keyword.arg != "repo_root":
                    continue
                checked += 1
                segment = _segment(source, keyword.value)
                assert "__file__" not in segment, (
                    "deferred fan-out 再展開の repo_root には作業リポジトリのルートを渡してください: "
                    f"{segment}"
                )
        assert checked, "DAGExecutor の repo_root 引数が見つかりません"

    def test_fleet_wave_runner_repo_root_is_not_the_package_root(self) -> None:
        source, tree = _orchestrator_ast()
        targets = [
            node
            for node in ast.walk(tree)
            if isinstance(node, ast.FunctionDef) and node.name == "_build_fleet_wave_runner"
        ]
        assert targets, "_build_fleet_wave_runner が見つかりません"
        checked = 0
        for func in targets:
            for node in ast.walk(func):
                if not isinstance(node, ast.Assign):
                    continue
                names = [t.id for t in node.targets if isinstance(t, ast.Name)]
                if "repo_root" not in names:
                    continue
                checked += 1
                segment = _segment(source, node.value)
                assert "__file__" not in segment, (
                    "Fleet wave prompt の repo_root には作業リポジトリのルートを渡してください: "
                    f"{segment}"
                )
        assert checked, "_build_fleet_wave_runner の repo_root 代入が見つかりません"

    def test_fleet_collector_receives_wave_step_ids(self) -> None:
        """FR-RTO-07: Wave の Step 集合を FleetEventCollector へ注入する。

        注入がないと worker → Step の対応を照合する対象集合が存在せず、
        Fleet 経路の消費は常に帰属不能となる。
        """
        source, tree = _orchestrator_ast()
        targets = [
            node
            for node in ast.walk(tree)
            if isinstance(node, ast.FunctionDef) and node.name == "_build_fleet_wave_runner"
        ]
        assert targets, "_build_fleet_wave_runner が見つかりません"
        calls = [
            node
            for func in targets
            for node in ast.walk(func)
            if isinstance(node, ast.Call)
            and isinstance(node.func, ast.Name)
            and node.func.id == "FleetEventCollector"
        ]
        assert calls, "_build_fleet_wave_runner 内の FleetEventCollector 生成が見つかりません"
        for call in calls:
            keywords = {kw.arg for kw in call.keywords}
            assert "step_ids" in keywords, (
                "FleetEventCollector へ Wave の Step 集合 (step_ids) を注入してください: "
                f"{_segment(source, call)}"
            )
