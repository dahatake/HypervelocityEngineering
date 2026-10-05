"""FR-KIT-01 / FR-KIT-04: markdown-query 配布キットの構成契約。

根拠: hve-dev/requirement-definition.md §3.10

RED（実装前）:
  - `launch.py` が存在しない ``gui`` トップレベルパッケージを import する
  - `pyproject.toml` が ``gui*`` を配布対象に宣言している
  - CLI ランチャと設定生成が存在しない
  - vendor に GUI とレポート生成が同梱されていない
"""

from __future__ import annotations

from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).resolve().parents[2]
_KIT = _REPO_ROOT / "tools" / "skills" / "markdown_query"
_VENDOR = _KIT / "vendor" / "mdq"


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


class TestKitEntryPoints:
    def test_launcher_uses_the_vendored_engine_package(self) -> None:
        src = _read(_KIT / "launch.py")
        assert "from mdq.gui.__main__ import main" in src
        assert "from gui.__main__" not in src

    def test_launcher_fails_closed_when_vendor_gui_is_missing(self) -> None:
        src = _read(_KIT / "launch.py")
        assert 'vendor / "mdq" / "gui" / "__main__.py"' in src

    def test_packaging_declares_the_vendored_engine(self) -> None:
        src = _read(_KIT / "pyproject.toml")
        assert 'where = ["vendor"]' in src
        assert 'include = ["mdq*"]' in src
        assert 'markdown-query-gui = "mdq.gui.__main__:main"' in src

    def test_kit_no_longer_owns_a_gui_package(self) -> None:
        assert not (_KIT / "gui").exists()

    @pytest.mark.parametrize("name", ["mdq.ps1", "mdq.sh", "mdq.cmd"])
    def test_cli_launchers_exist(self, name: str) -> None:
        assert (_KIT / name).is_file()

    def test_config_scaffolder_exists(self) -> None:
        assert (_KIT / "init_config.py").is_file()


class TestVendorContents:
    @pytest.mark.parametrize(
        "rel",
        [
            "gui/__main__.py",
            "gui/settings_section.py",
            "gui/index_service.py",
            "gui/settings_store.py",
            "usage_report.py",
        ],
    )
    def test_vendor_ships_the_gui_and_report_generator(self, rel: str) -> None:
        assert (_VENDOR / rel).is_file()

    def test_vendor_excludes_tests_at_any_depth(self) -> None:
        offenders = [
            p.relative_to(_VENDOR).as_posix()
            for p in _VENDOR.rglob("*")
            if p.is_file() and "tests" in p.relative_to(_VENDOR).parts
        ]
        assert offenders == []


class TestReportOutputIsRepositoryLocal:
    def test_default_output_dir_is_under_dot_mdq(self, tmp_path: Path) -> None:
        from mdq import usage_report

        out = usage_report.default_output_dir(tmp_path)
        assert out == (tmp_path / ".mdq" / "usage-report").resolve()


class TestSkillPortability:
    """FR-KIT-02: measured HVE data stays in optional, excluded references."""

    @pytest.mark.parametrize("relative", ["SKILL.md", "examples/prompt-snippets.md"])
    def test_hve_measurements_are_isolated_from_portable_guidance(self, relative: str) -> None:
        canonical = _REPO_ROOT / ".github/skills/markdown-query"
        portable = _read(canonical / relative)
        hve_reference = _read(canonical / "references/repo-specific/hve-integration.md")
        for measured_value in ("250,823", "480.8", "323.2", "99.81", "99.87"):
            assert measured_value not in portable
            assert measured_value in hve_reference
        assert "自リポジトリ" in portable

    def test_cli_guidance_does_not_assume_an_hve_background_watcher(self) -> None:
        canonical = _REPO_ROOT / ".github/skills/markdown-query"
        reference = _read(canonical / "references/cli-reference.md")
        assert "通常は本コマンドを手動起動する必要はない" not in reference
        assert "HVE リポジトリでの宣言例は" not in reference
        assert "--root" in reference
        assert "--initial-index" in reference
        assert "Ctrl+C" in reference
