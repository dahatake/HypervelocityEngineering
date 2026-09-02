"""FR-GUI-04: Code-Query の別リポジトリ向け独立管理画面契約。

Markdown-Query の standalone GUI と同様に、配布キットだけを別リポジトリへ
コピーして利用できること、および HVE 組み込み画面と実装を共有することを固定する。
"""

from __future__ import annotations

import configparser
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

pytest.importorskip("PySide6")

REPO_ROOT = Path(__file__).resolve().parents[3]
BUNDLE_ROOT = REPO_ROOT / "tools" / "skills" / "code_query"

# Mirrors the drop list in tools/skills/_kit/kit_sync.py.
_VENDOR_EXCLUDES = (
    "tests",
    "__pycache__",
    ".mypy_cache",
    "golden-queries.json",
    "golden-queries-holdout.json",
)
_SHARED_SYNC = REPO_ROOT / "tools" / "skills" / "_kit" / "kit_sync.py"


def _shared_drop_names() -> set[str]:
    """Artifact names that the shared sync implementation deletes."""
    text = _SHARED_SYNC.read_text(encoding="utf-8")
    names: set[str] = set()
    for const in ("DROP_DIR_NAMES", "DROP_FILE_NAMES"):
        match = re.search(rf"^{const} = \(([^)]*)\)", text, re.MULTILINE)
        assert match, f"{const} not found in {_SHARED_SYNC}"
        names |= set(re.findall(r'"([^"]+)"', match.group(1)))
    return names


@pytest.fixture(scope="module")
def qapp():
    from PySide6.QtWidgets import QApplication

    yield QApplication.instance() or QApplication([])


@pytest.fixture()
def repo(tmp_path: Path) -> Path:
    subprocess.run(["git", "init", "-q"], cwd=tmp_path, check=True)
    (tmp_path / "cq.toml").write_text(
        "[profiles.main]\nroots = ['pkg']\n",
        encoding="utf-8",
    )
    (tmp_path / "pkg").mkdir()
    (tmp_path / "pkg" / "sample.py").write_text(
        "def sample():\n    return 1\n", encoding="utf-8"
    )
    return tmp_path


class TestStandaloneSettings:
    def test_non_hve_repository_uses_repository_local_settings(
        self, repo: Path
    ) -> None:
        from cq.gui import settings_store

        assert settings_store.detect_settings_path(repo) == (
            repo / ".cq-gui-settings.txt"
        )

    def test_hve_repository_reuses_the_hve_settings_path(self, tmp_path: Path) -> None:
        from cq.gui import settings_store

        (tmp_path / "hve").mkdir()

        assert settings_store.detect_settings_path(tmp_path) == (
            tmp_path / "hve" / ".settings.txt"
        )

    def test_save_preserves_sections_and_options_not_owned_by_cq(
        self, repo: Path
    ) -> None:
        from cq.gui import settings_store

        path = settings_store.detect_settings_path(repo)
        path.write_text(
            "[foreign]\nmode = keep\n\n[options]\ntheme = dark\n",
            encoding="utf-8",
        )
        settings = settings_store.load(repo)
        settings["cq"]["profile"] = "main"
        settings["cq"]["build_profiles"] = "main"
        settings["options"]["cq_watch"] = "off"
        settings["options"]["cq_watch_debounce_ms"] = 750

        settings_store.save(repo, settings)

        parsed = configparser.ConfigParser()
        parsed.read(path, encoding="utf-8")
        assert parsed["foreign"]["mode"] == "keep"
        assert parsed["options"]["theme"] == "dark"
        assert parsed["options"]["cq_watch"] == "off"
        assert parsed["options"].getint("cq_watch_debounce_ms") == 750
        assert parsed["cq"]["profile"] == "main"


class TestStandaloneWindow:
    def test_window_identifies_the_selected_repository(
        self, qapp, repo: Path
    ) -> None:
        from cq.gui.standalone_window import StandaloneWindow

        window = StandaloneWindow(repo_root=repo)

        assert window.repo_root == repo.resolve()
        assert str(repo.resolve()) in window.windowTitle()
        assert window._section._repo_root == repo.resolve()
        window.close()

    def test_watch_settings_round_trip_without_hve_settings_window(
        self, qapp, repo: Path
    ) -> None:
        from cq.gui import settings_store
        from cq.gui.settings_section import CqIndexSection

        settings = settings_store.load(repo)
        settings["options"]["cq_watch"] = "off"
        settings["options"]["cq_watch_debounce_ms"] = 640
        settings_store.save(repo, settings)

        section = CqIndexSection(repo_root=repo)
        assert section.cq_watch.get_tristate() is False
        assert section.cq_watch_debounce_ms.value() == 640

        section.cq_watch.set_tristate(True)
        section.cq_watch_debounce_ms.setValue(900)

        reloaded = settings_store.load(repo)
        assert reloaded["options"]["cq_watch"] == "on"
        assert reloaded["options"]["cq_watch_debounce_ms"] == 900
        section.close()


class TestSharedImplementation:
    def test_hve_compatibility_modules_reexport_the_shared_implementation(self) -> None:
        from cq.gui import index_service as shared_service
        from cq.gui.settings_section import CqIndexSection as SharedSection
        from cq.gui.threads import CqIndexBuildThread as SharedThread
        from hve.gui import cq_index_service as hve_service
        from hve.gui.cq_settings_section import CqIndexSection as HveSection
        from hve.gui.cq_threads import CqIndexBuildThread as HveThread

        assert issubclass(HveSection, SharedSection)
        assert HveThread is SharedThread
        assert hve_service.list_profiles is shared_service.list_profiles
        assert hve_service.build is shared_service.build


class TestPortableBundle:
    @staticmethod
    def _copy_bundle(tmp_path: Path) -> Path:
        bundle = tmp_path / "code-query"
        vendor = bundle / "vendor"
        vendor.mkdir(parents=True)
        shutil.copy2(BUNDLE_ROOT / "launch.py", bundle / "launch.py")
        shutil.copytree(
            REPO_ROOT / "cq",
            vendor / "cq",
            ignore=shutil.ignore_patterns(*_VENDOR_EXCLUDES),
        )
        return bundle

    def test_fixture_excludes_exactly_what_sync_vendor_drops(self) -> None:
        """配布物の除外規約を fixture と共有同期実装で分岐させない。"""
        assert _shared_drop_names() == set(_VENDOR_EXCLUDES), (
            "tools/skills/_kit/kit_sync.py and this fixture disagree on what the "
            "portable bundle must exclude; the bundle under test would stop "
            "matching the bundle that sync-vendor actually ships"
        )

    def test_launcher_reports_version_without_the_hve_import_path(
        self, tmp_path: Path
    ) -> None:
        bundle = self._copy_bundle(tmp_path)
        external_repo = tmp_path / "external"
        external_repo.mkdir()
        env = dict(os.environ)
        env.pop("PYTHONPATH", None)

        completed = subprocess.run(
            [sys.executable, "-S", str(bundle / "launch.py"), "--version"],
            cwd=external_repo,
            env=env,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
        )

        assert completed.returncode == 0, completed.stderr
        assert "code-query-gui" in completed.stdout

    def test_vendored_service_reads_an_external_repository_config(
        self, tmp_path: Path, repo: Path
    ) -> None:
        bundle = self._copy_bundle(tmp_path)
        env = dict(os.environ)
        env.pop("PYTHONPATH", None)
        code = (
            "import sys; "
            f"sys.path.insert(0, {str(bundle / 'vendor')!r}); "
            "from cq.gui import index_service; "
            f"result=index_service.list_profiles(__import__('pathlib').Path({str(repo)!r})); "
            "print(','.join(result['profiles']))"
        )

        completed = subprocess.run(
            [sys.executable, "-S", "-c", code],
            cwd=repo,
            env=env,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
        )

        assert completed.returncode == 0, completed.stderr
        assert completed.stdout.strip() == "main"

    def test_cross_platform_launchers_and_package_metadata_are_shipped(self) -> None:
        expected = {
            "launch.py",
            "launch-gui.cmd",
            "launch-gui.ps1",
            "launch-gui.sh",
            "pyproject.toml",
        }

        assert expected <= {path.name for path in BUNDLE_ROOT.iterdir()}
