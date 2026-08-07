"""FR-KIT-04: 配布フォルダをコピーしただけで Skill が成立することを検証する。

根拠: hve-dev/requirement-definition.md §3.10 FR-KIT-04

**版管理下の実配布物**をコピーして検証する。正本（`mdq/` / `cq/`）から検証時に
複製した一時ツリーで代替すると、同期漏れを検出できなくなるため行わない。

依存インストール（venv 作成 + pip）は `--no-venv` で省略する。ネットワークと
実行時間に依存させないためであり、本テストの対象はキットの自己完結性
（同梱エンジンの解決、設定生成、Skill 配置、CLI / GUI 導線）である。
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).resolve().parents[2]

_KITS = (
    pytest.param(
        "code_query", "cq", "code-query", "cq.toml",
        # CQ_PROFILE を渡さない。生成された cq.toml が単一 profile なので、
        # コピーしただけで検索が成立しなければならない（FR-KIT-04）。
        ["search", "--q", "deploy_pipeline"], {},
        id="code-query",
    ),
    pytest.param(
        "markdown_query", "mdq", "markdown-query", "mdq.toml",
        # grep モードは字句一致で決定的。BM25 のランキングに依存させない。
        ["search", "--q", "deployment", "--mode", "grep"], {},
        id="markdown-query",
    ),
)

_COPY_IGNORE = shutil.ignore_patterns(
    "__pycache__", ".pytest_cache", ".venv-*", "*.pyc"
)


def _clean_env(
    *,
    extra_pythonpath: str | None = None,
    overrides: dict[str, str] | None = None,
) -> dict[str, str]:
    """上流リポジトリを import 経路から外した環境を返す。"""
    env = dict(os.environ)
    env.pop("PYTHONPATH", None)
    env["PYTHONNOUSERSITE"] = "1"
    if extra_pythonpath:
        env["PYTHONPATH"] = extra_pythonpath
    if overrides:
        env.update(overrides)
    return env


@pytest.fixture()
def target_repo(tmp_path: Path) -> Path:
    repo = tmp_path / "target-repo"
    (repo / "docs").mkdir(parents=True)
    (repo / "pkg").mkdir()
    (repo / "docs" / "guide.md").write_text(
        "# Guide\n\n## Deployment\n\nrun the deployment pipeline.\n",
        encoding="utf-8",
    )
    (repo / "pkg" / "service.py").write_text(
        "def deploy_pipeline():\n    return 'deployed'\n",
        encoding="utf-8",
    )
    subprocess.run(["git", "init", "-q"], cwd=repo, check=True)
    return repo


def _copy_kit(kit_name: str, tmp_path: Path) -> Path:
    source = _REPO_ROOT / "tools" / "skills" / kit_name
    target = tmp_path / "copied-kit"
    shutil.copytree(source, target, ignore=_COPY_IGNORE)
    return target


@pytest.mark.parametrize("kit_name,engine,skill,config,search_argv,env_overrides", _KITS)
class TestPortableKit:
    def test_setup_configures_a_fresh_repository(
        self, kit_name: str, engine: str, skill: str, config: str,
        search_argv: list[str], env_overrides: dict[str, str],
        tmp_path: Path, target_repo: Path,
    ) -> None:
        kit = _copy_kit(kit_name, tmp_path)
        result = subprocess.run(
            [
                sys.executable, str(kit / "kit" / "kit_setup.py"),
                "--kit-dir", str(kit),
                "--repo-root", str(target_repo),
                "--no-venv", "--install-skill", "--build-index",
                "--python", sys.executable,
            ],
            cwd=str(target_repo),
            env=_clean_env(),
            capture_output=True,
            text=True,
        )
        assert result.returncode == 0, result.stderr

        # P4: 設定ファイルが生成される
        assert (target_repo / config).is_file()

        # P3: Skill 定義が配置され、同梱コピーと一致する
        installed = target_repo / ".github" / "skills" / skill / "SKILL.md"
        assert installed.is_file()
        assert installed.read_bytes() == (kit / "skill" / "SKILL.md").read_bytes()

        # P1: 上流非依存で索引と検索が動く
        search = subprocess.run(
            [sys.executable, "-m", engine, *search_argv],
            cwd=str(target_repo),
            env=_clean_env(
                extra_pythonpath=str(kit / "vendor"), overrides=env_overrides
            ),
            capture_output=True,
            text=True,
        )
        assert search.returncode == 0, search.stderr
        assert search.stdout.strip(), "the copied kit returned no search result"

    def test_engine_resolves_from_the_bundled_copy_without_upstream(
        self, kit_name: str, engine: str, skill: str, config: str,
        search_argv: list[str], env_overrides: dict[str, str],
        tmp_path: Path, target_repo: Path,
    ) -> None:
        """P2 / P6: 同梱エンジンが使われ、`hve` を import しない。"""
        kit = _copy_kit(kit_name, tmp_path)
        probe = (
            "import importlib, json, sys\n"
            "mod = importlib.import_module(sys.argv[1])\n"
            "leaked = sorted(m for m in sys.modules if m == 'hve' or m.startswith('hve.'))\n"
            "print(json.dumps({'file': mod.__file__, 'leaked': leaked}))\n"
        )
        result = subprocess.run(
            [sys.executable, "-c", probe, engine],
            cwd=str(target_repo),
            env=_clean_env(extra_pythonpath=str(kit / "vendor")),
            capture_output=True,
            text=True,
        )
        assert result.returncode == 0, result.stderr
        payload = json.loads(result.stdout.strip().splitlines()[-1])
        assert Path(payload["file"]).is_relative_to(kit / "vendor"), payload["file"]
        assert payload["leaked"] == [], payload["leaked"]

    def test_gui_launcher_is_present_and_reports_its_version(
        self, kit_name: str, engine: str, skill: str, config: str,
        search_argv: list[str], env_overrides: dict[str, str],
        tmp_path: Path, target_repo: Path,
    ) -> None:
        """P5: GUI 起動導線が存在する（依存未導入なら手順を示して fail-closed）。"""
        pytest.importorskip("PySide6")
        kit = _copy_kit(kit_name, tmp_path)
        result = subprocess.run(
            [sys.executable, str(kit / "launch.py"), "--version"],
            cwd=str(target_repo),
            env=_clean_env(),
            capture_output=True,
            text=True,
        )
        assert result.returncode == 0, result.stderr + result.stdout
        assert "gui" in result.stdout.lower()

    def test_kit_ships_launchers_for_every_supported_os(
        self, kit_name: str, engine: str, skill: str, config: str,
        search_argv: list[str], env_overrides: dict[str, str],
        tmp_path: Path,
    ) -> None:
        """P7: OS 別ランチャが揃っている（判断ロジックは共有実装側）。"""
        kit = _copy_kit(kit_name, tmp_path)
        for name in (
            "setup.ps1", "setup.sh",
            "launch-gui.ps1", "launch-gui.sh", "launch-gui.cmd",
            f"{engine}.ps1", f"{engine}.sh", f"{engine}.cmd",
        ):
            assert (kit / name).is_file(), f"{kit_name} is missing {name}"
