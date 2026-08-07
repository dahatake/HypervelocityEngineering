"""他リポジトリ配布（`tools/for-other-repo/`）の同期契約。

配布パッケージは「宣言（`package.toml`）を単一の出所とし、コピー時に組み立てる」
方式なので、検証対象は **`copy_to_repo.py` が実際に生成した成果物** とする
（FR-KIT-04 の先例に倣い、正本から検証時に複製した一時ツリーで代替しない）。
"""

from __future__ import annotations

import importlib.util
import json
import os
import subprocess
import sys
import tomllib
from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).resolve().parents[2]
_PACKAGES_DIR = _REPO_ROOT / "tools" / "for-other-repo"
_MANIFEST = "KIT-VERSION.json"
_PACKAGE_NAMES = ("markdown-query", "code-query", "tool-search")


def _load_copy_module():
    """`tools/for-other-repo/copy_to_repo.py` は package ではないのでパスから読む。"""
    path = _PACKAGES_DIR / "copy_to_repo.py"
    spec = importlib.util.spec_from_file_location("_for_other_repo_copy", path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


copy_to_repo = _load_copy_module()


@pytest.fixture(scope="module")
def packages() -> dict:
    return copy_to_repo.discover_packages()


@pytest.fixture(scope="module")
def copied(tmp_path_factory) -> Path:
    """3 パッケージを 1 度だけコピーして使い回す。"""
    dest = tmp_path_factory.mktemp("for-other-repo")
    assert copy_to_repo.main([str(dest)]) == 0
    return dest


@pytest.fixture()
def preserved_policy(copied: Path):
    """temp 内の policy.json を変更しても後続テストへ残さない。

    preserve 対象は再コピーでも上書きされないので、テスト側で戻す。
    """
    path = copied / "tool-search" / "vendor" / "toolsearch" / "policy.json"
    original = path.read_bytes()
    try:
        yield path
    finally:
        path.write_bytes(original)


class TestDeclarations:
    """宣言だけが出所であることを守る。"""

    def test_every_expected_package_is_declared(self, packages: dict) -> None:
        assert set(packages) == set(_PACKAGE_NAMES)

    @pytest.mark.parametrize("name", _PACKAGE_NAMES)
    def test_required_keys_are_present(self, packages: dict, name: str) -> None:
        package = packages[name]
        for key in ("name", "version", "engine"):
            assert package.get(key), f"{name}: package.{key} is missing"
        assert copy_to_repo.parse_version(package["version"]) >= (1,)

    @pytest.mark.parametrize("name", _PACKAGE_NAMES)
    def test_declared_sources_exist(self, packages: dict, name: str) -> None:
        for source in packages[name].get("sources", []):
            assert (_REPO_ROOT / source["from"]).exists(), source["from"]
        for doc in packages[name].get("docs", []):
            assert (_REPO_ROOT / doc["from"]).exists(), doc["from"]

    def test_engine_implementations_are_not_duplicated_here(self) -> None:
        """エンジン実体を配布宣言側へ複製しない（正本は上流の 1 箇所）。"""
        declared = {
            (_PACKAGES_DIR / name).resolve()
            for name in _PACKAGE_NAMES
        }
        for package_dir in declared:
            assert not (package_dir / "vendor").exists(), package_dir


class TestStagedContent:
    """配布物に混ぜてはならないものが混ざらない。"""

    @pytest.mark.parametrize("name", _PACKAGE_NAMES)
    def test_no_build_artifacts_ship(self, copied: Path, name: str) -> None:
        for path in (copied / name).rglob("*"):
            if not path.is_file():
                continue
            parts = path.relative_to(copied / name).parts
            assert "__pycache__" not in parts
            assert not any(part.startswith(".venv") for part in parts)
            assert path.suffix not in (".pyc", ".pyo")

    @pytest.mark.parametrize("name", _PACKAGE_NAMES)
    def test_setup_entrypoints_ship(self, copied: Path, name: str) -> None:
        for entry in ("install.py", "install.ps1", "install.sh", "kit/kit_setup.py"):
            assert (copied / name / entry).is_file(), f"{name}/{entry}"

    def test_repository_specific_material_is_excluded(self, copied: Path) -> None:
        assert not (copied / "markdown-query" / "usage-report").exists()
        assert not (copied / "markdown-query" / "results").exists()

    def test_docs_ship_with_their_images(self, copied: Path) -> None:
        doc = copied / "markdown-query" / "docs" / "skills-markdown-query.md"
        assert doc.is_file()
        assert (
            copied / "markdown-query" / "docs" / "images" / "skills-markdown-query"
            / "architecture.svg"
        ).is_file()

    def test_extra_dependencies_ship_only_where_declared(
        self, copied: Path, packages: dict
    ) -> None:
        for name in _PACKAGE_NAMES:
            path = copied / name / "install-extras.json"
            if packages[name].get("extra_dependencies"):
                payload = json.loads(path.read_text(encoding="utf-8"))
                assert payload["packages"] == packages[name]["extra_dependencies"]
            else:
                assert not path.exists(), name


class TestVersionManifest:
    @pytest.mark.parametrize("name", _PACKAGE_NAMES)
    def test_manifest_records_what_was_shipped(
        self, copied: Path, packages: dict, name: str
    ) -> None:
        data = json.loads((copied / name / _MANIFEST).read_text(encoding="utf-8"))
        assert data["package"] == name
        assert data["version"] == packages[name]["version"]
        assert data["engine"] == packages[name]["engine"]
        assert data["file_count"] == len(data["files"])
        # 実在するファイルだけを記録する（マニフェスト自身は対象外）。
        assert _MANIFEST not in data["files"]
        for rel in data["files"]:
            assert (copied / name / rel).is_file(), rel

    def test_engine_version_comes_from_the_vendored_package(self, copied: Path) -> None:
        data = json.loads((copied / "markdown-query" / _MANIFEST).read_text(encoding="utf-8"))
        upstream = (_REPO_ROOT / "mdq" / "__init__.py").read_text(encoding="utf-8")
        assert f'__version__ = "{data["engine_version"]}"' in upstream


class TestVersionComparison:
    @pytest.mark.parametrize(
        "current,new,expected",
        [
            (None, "1.0.0", "new"),
            ({"version": "1.0.0"}, "1.0.1", "upgrade"),
            ({"version": "1.0.0"}, "1.0.0", "same"),
            ({"version": "1.1.0"}, "1.0.9", "downgrade"),
            ({"version": "1.9.0"}, "1.10.0", "upgrade"),
        ],
    )
    def test_status(self, current, new: str, expected: str) -> None:
        assert copy_to_repo.compare_versions(current, new) == expected


class TestVersionGate:
    def test_same_version_is_skipped_without_force(self, copied: Path, capsys) -> None:
        marker = copied / "tool-search" / "GETTING-STARTED.md"
        marker.write_text("locally edited\n", encoding="utf-8")
        assert copy_to_repo.main([str(copied), "-p", "tool-search"]) == 0
        assert "スキップ" in capsys.readouterr().out
        assert marker.read_text(encoding="utf-8") == "locally edited\n"

    def test_force_overwrites_the_same_version(self, copied: Path) -> None:
        marker = copied / "tool-search" / "GETTING-STARTED.md"
        marker.write_text("locally edited\n", encoding="utf-8")
        assert copy_to_repo.main([str(copied), "-p", "tool-search", "--force"]) == 0
        assert marker.read_text(encoding="utf-8") != "locally edited\n"

    def test_newer_destination_is_not_downgraded(self, copied: Path, capsys) -> None:
        path = copied / "tool-search" / _MANIFEST
        data = json.loads(path.read_text(encoding="utf-8"))
        data["version"] = "99.0.0"
        path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
        assert copy_to_repo.main([str(copied), "-p", "tool-search"]) == 0
        assert "downgrade" in capsys.readouterr().out
        assert json.loads(path.read_text(encoding="utf-8"))["version"] == "99.0.0"
        # 後続テストのために版を戻す。
        assert copy_to_repo.main([str(copied), "-p", "tool-search", "--force"]) == 0


class TestPreserveAndPrune:
    def test_preserved_files_are_not_overwritten(
        self, copied: Path, preserved_policy: Path
    ) -> None:
        tuned = json.loads(preserved_policy.read_text(encoding="utf-8"))
        tuned["limit"] = 3
        preserved_policy.write_text(json.dumps(tuned, ensure_ascii=False), encoding="utf-8")
        assert copy_to_repo.main([str(copied), "-p", "tool-search", "--force"]) == 0
        assert json.loads(preserved_policy.read_text(encoding="utf-8"))["limit"] == 3

    def test_files_dropped_from_the_declaration_are_removed(self, copied: Path) -> None:
        docs = copied / "tool-search" / "docs"
        assert docs.is_dir()
        assert copy_to_repo.main([str(copied), "-p", "tool-search", "--force", "--no-docs"]) == 0
        assert not docs.exists()
        assert copy_to_repo.main([str(copied), "-p", "tool-search", "--force"]) == 0
        assert (docs / "tool-search.md").is_file()

    def test_unmanaged_files_survive_a_resync(self, copied: Path) -> None:
        """利用者が作った venv や設定を配布側が消さない。"""
        stray = copied / "tool-search" / ".venv-toolsearch" / "marker.txt"
        stray.parent.mkdir(parents=True, exist_ok=True)
        stray.write_text("keep me\n", encoding="utf-8")
        assert copy_to_repo.main([str(copied), "-p", "tool-search", "--force"]) == 0
        assert stray.read_text(encoding="utf-8") == "keep me\n"


class TestDriftDetection:
    def test_modified_and_missing_files_are_reported(self, copied: Path) -> None:
        target = copied / "tool-search"
        manifest = json.loads((target / _MANIFEST).read_text(encoding="utf-8"))
        (target / "GETTING-STARTED.md").write_text("changed\n", encoding="utf-8")
        (target / "toolsearch.cmd").unlink()
        drift = copy_to_repo.local_modifications(target, manifest)
        assert "GETTING-STARTED.md (改変)" in drift
        assert "toolsearch.cmd (欠落)" in drift
        assert copy_to_repo.main([str(copied), "-p", "tool-search", "--force"]) == 0
        restored = json.loads((target / _MANIFEST).read_text(encoding="utf-8"))
        assert copy_to_repo.local_modifications(target, restored) == []

    def test_preserved_files_are_not_reported_as_drift(
        self, copied: Path, preserved_policy: Path
    ) -> None:
        target = copied / "tool-search"
        tuned = json.loads(preserved_policy.read_text(encoding="utf-8"))
        tuned["tau"] = 0.25
        preserved_policy.write_text(json.dumps(tuned, ensure_ascii=False), encoding="utf-8")
        assert copy_to_repo.main([str(copied), "-p", "tool-search", "--force"]) == 0
        manifest = json.loads((target / _MANIFEST).read_text(encoding="utf-8"))
        assert "vendor/toolsearch/policy.json" in manifest["preserved"]
        assert copy_to_repo.local_modifications(target, manifest) == []

    def test_install_py_verifies_without_the_upstream_repository(self, copied: Path) -> None:
        kit = copied / "tool-search"
        result = subprocess.run(
            [sys.executable, str(kit / "install.py"), "--kit-dir", str(kit), "--verify"],
            capture_output=True, text=True, encoding="utf-8",
            env=_utf8_env(),
        )
        assert result.returncode == 0, (result.stdout or "") + (result.stderr or "")
        assert "改変・欠落 0 件" in result.stdout

        (kit / "GETTING-STARTED.md").write_text("changed\n", encoding="utf-8")
        broken = subprocess.run(
            [sys.executable, str(kit / "install.py"), "--kit-dir", str(kit), "--verify"],
            capture_output=True, text=True, encoding="utf-8",
            env=_utf8_env(),
        )
        assert broken.returncode == 1
        assert "GETTING-STARTED.md" in broken.stdout
        assert copy_to_repo.main([str(copied), "-p", "tool-search", "--force"]) == 0

    def test_install_py_reports_the_version(self, copied: Path) -> None:
        kit = copied / "tool-search"
        result = subprocess.run(
            [sys.executable, str(kit / "install.py"), "--kit-dir", str(kit), "--version"],
            capture_output=True, text=True, encoding="utf-8",
            env=_utf8_env(),
        )
        assert result.returncode == 0
        assert "tool-search" in result.stdout


class TestBareOsCompatibility:
    """素の OS で成立させるための、実機検証から得た契約。"""

    @pytest.mark.parametrize("name", _PACKAGE_NAMES)
    def test_shipped_powershell_is_ascii_only(self, copied: Path, name: str) -> None:
        """Windows PowerShell 5.1 は .ps1 を ANSI として読む。

        素の Windows には 5.1 しか無いため、UTF-8(BOM 無し)の非 ASCII を含む
        .ps1 は起動前にパースエラーになる（Windows Sandbox で実測）。
        """
        for path in (copied / name).glob("*.ps1"):
            text = path.read_text(encoding="utf-8")
            offenders = sorted({ch for ch in text if ord(ch) > 127})
            assert not offenders, f"{path.name}: {offenders}"

    @pytest.mark.parametrize("name", _PACKAGE_NAMES)
    def test_install_sh_checks_venv_support(self, copied: Path, name: str) -> None:
        """Debian / Ubuntu は python3 と venv 用パッケージが別。

        インタプリタの有無だけを見ると `python3 -m venv` で落ちる
        （Ubuntu 24.04 / WSL2 で実測）。
        """
        text = (copied / name / "install.sh").read_text(encoding="utf-8")
        assert "import ensurepip" in text
        assert "--no-venv" in text

    @pytest.mark.parametrize("name", _PACKAGE_NAMES)
    def test_shipped_shell_scripts_use_lf(self, copied: Path, name: str) -> None:
        for path in (copied / name).glob("*.sh"):
            assert b"\r\n" not in path.read_bytes(), path.name


def _utf8_env() -> dict[str, str]:
    env = dict(os.environ)
    env["PYTHONIOENCODING"] = "utf-8"
    return env


def _clean_env(vendor: Path) -> dict[str, str]:
    """上流リポジトリを import 経路から外した環境。"""
    env = _utf8_env()
    env["PYTHONPATH"] = str(vendor)
    env["PYTHONNOUSERSITE"] = "1"
    return env


class TestToolSearchPortability:
    """FR-KIT-04 / FR-KIT-05 と同じ趣旨: コピーしただけで成立すること。

    `cwd` を上流リポジトリにすると `mdq` / `toolsearch` が上流側へ解決され、
    同梱漏れを検出できない（実際 `mdq.search` の同梱漏れを見逃した）。
    必ずコピー先を `cwd` とし、リポジトリは `--repo-root` で明示する。
    """

    @pytest.mark.parametrize(
        "argv",
        [["policy"], ["skills", "--repo-root", str(_REPO_ROOT)],
         ["eval", "--repo-root", str(_REPO_ROOT)]],
    )
    def test_cli_runs_without_the_upstream_package(
        self, copied: Path, argv: list[str]
    ) -> None:
        kit = copied / "tool-search"
        result = subprocess.run(
            [sys.executable, "-m", "toolsearch", *argv],
            cwd=str(copied),
            env=_clean_env(kit / "vendor"),
            capture_output=True, text=True, encoding="utf-8",
        )
        assert result.returncode == 0, (result.stdout or "") + (result.stderr or "")

    def test_eval_reports_recall_and_token_reduction(self, copied: Path) -> None:
        kit = copied / "tool-search"
        result = subprocess.run(
            [sys.executable, "-m", "toolsearch", "eval", "--repo-root", str(_REPO_ROOT)],
            cwd=str(copied),
            env=_clean_env(kit / "vendor"),
            capture_output=True, text=True, encoding="utf-8",
        )
        assert result.returncode == 0, (result.stdout or "") + (result.stderr or "")
        for label in ("recall@5", "MRR", "reduction"):
            assert label in result.stdout

    def test_no_upstream_import_survives_in_the_vendored_engine(self, copied: Path) -> None:
        vendor = copied / "tool-search" / "vendor" / "toolsearch"
        for path in vendor.rglob("*.py"):
            text = path.read_text(encoding="utf-8")
            assert "from hve" not in text, path
            assert "import hve" not in text, path

    def test_every_upstream_module_the_engine_imports_is_vendored(
        self, copied: Path
    ) -> None:
        """`mdq.search` の同梱漏れを見逃した回帰テスト。

        遅延 import（関数内の `from mdq.x import y`）は静的に見ないと
        実行経路を通すまで表面化しない。
        """
        import re

        vendor = copied / "tool-search" / "vendor"
        wanted: set[str] = set()
        pattern = re.compile(r"from\s+mdq\.(\w+)\s+import|from\s+mdq\s+import\s+(\w+)")
        for path in (vendor / "toolsearch").rglob("*.py"):
            for match in pattern.finditer(path.read_text(encoding="utf-8")):
                wanted.add(match.group(1) or match.group(2))
        assert wanted, "mdq への参照が 1 つも無いのは想定外"
        for module in sorted(wanted):
            assert (vendor / "mdq" / f"{module}.py").is_file(), module


class TestKitManifests:
    @pytest.mark.parametrize("name", _PACKAGE_NAMES)
    def test_kit_toml_declares_what_install_py_reads(self, copied: Path, name: str) -> None:
        kit = tomllib.loads((copied / name / "kit.toml").read_text(encoding="utf-8"))["kit"]
        for key in ("engine", "skill", "venv", "config"):
            assert kit.get(key), f"{name}: kit.{key} is missing"

    def test_tool_search_ships_no_skill_definition(self, copied: Path) -> None:
        """Skill ではなくライブラリなので `.github/skills/` へ配置しない。"""
        assert not (copied / "tool-search" / "skill").exists()
        kit = tomllib.loads(
            (copied / "tool-search" / "kit.toml").read_text(encoding="utf-8")
        )["kit"]
        assert kit["supports_index"] is False

    @pytest.mark.parametrize("name", ("markdown-query", "code-query"))
    def test_search_kits_ship_their_skill_definition(self, copied: Path, name: str) -> None:
        assert (copied / name / "skill" / "SKILL.md").is_file()
