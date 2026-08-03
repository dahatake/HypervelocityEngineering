"""FR-KIT-03: セットアップ・同期の判断ロジックを単一実装とする。

根拠: hve-dev/requirement-definition.md §3.10 FR-KIT-03

RED（実装前）:
  - `tools/skills/_kit/` が存在しない
  - `setup.ps1` / `setup.sh` が venv 作成・依存インストール・Skill 配置を OS 別に重複実装している
"""

from __future__ import annotations

from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).resolve().parents[2]
_SHARED = _REPO_ROOT / "tools" / "skills" / "_kit"
_KITS = ("tools/skills/code_query", "tools/skills/markdown_query")
_SHARED_MODULES = ("kit_setup.py", "kit_sync.py")

# OS 別スクリプトに残っていてはならない判断ロジックの痕跡。
_LOGIC_MARKERS = ("pip install", "-m venv", ".github/skills", "golden-queries.json")


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


class TestSharedImplementationExists:
    @pytest.mark.parametrize("name", _SHARED_MODULES)
    def test_shared_module_exists(self, name: str) -> None:
        assert (_SHARED / name).is_file()

    @pytest.mark.parametrize("kit_rel", _KITS)
    def test_kit_declares_its_parameters(self, kit_rel: str) -> None:
        import tomllib

        manifest = _REPO_ROOT / kit_rel / "kit.toml"
        assert manifest.is_file()
        data = tomllib.loads(manifest.read_text(encoding="utf-8"))
        kit = data["kit"]
        for key in ("engine", "skill", "venv"):
            assert kit.get(key), f"{kit_rel}/kit.toml is missing kit.{key}"


class TestSharedImplementationIsDistributed:
    @pytest.mark.parametrize("kit_rel", _KITS)
    def test_bundled_copy_matches_the_shared_source(self, kit_rel: str) -> None:
        bundled = _REPO_ROOT / kit_rel / "kit"
        for name in _SHARED_MODULES:
            shipped = bundled / name
            assert shipped.is_file(), (
                f"{kit_rel}/kit/{name} is missing; run sync-vendor to refresh it"
            )
            assert shipped.read_bytes() == (_SHARED / name).read_bytes(), (
                f"{kit_rel}/kit/{name} drifted from tools/skills/_kit/{name}"
            )

    @pytest.mark.parametrize("kit_rel", _KITS)
    def test_bundled_copy_carries_nothing_extra(self, kit_rel: str) -> None:
        bundled = _REPO_ROOT / kit_rel / "kit"
        shipped = sorted(
            p.relative_to(bundled).as_posix()
            for p in bundled.rglob("*")
            if p.is_file() and "__pycache__" not in p.relative_to(bundled).parts
        )
        expected = sorted(
            p.relative_to(_SHARED).as_posix()
            for p in _SHARED.rglob("*")
            if p.is_file() and "__pycache__" not in p.relative_to(_SHARED).parts
        )
        assert shipped == expected


class TestOsScriptsOnlyDelegate:
    @pytest.mark.parametrize("kit_rel", _KITS)
    @pytest.mark.parametrize("script", ("setup.ps1", "setup.sh"))
    def test_setup_delegates_to_the_shared_implementation(
        self, kit_rel: str, script: str
    ) -> None:
        text = _read(_REPO_ROOT / kit_rel / script)
        assert "kit_setup.py" in text
        for marker in _LOGIC_MARKERS:
            assert marker not in text, (
                f"{kit_rel}/{script} still owns decision logic ({marker!r}); "
                "move it into tools/skills/_kit/"
            )

    @pytest.mark.parametrize("kit_rel", _KITS)
    @pytest.mark.parametrize("script", ("sync-vendor.ps1", "sync-vendor.sh"))
    def test_sync_delegates_to_the_shared_implementation(
        self, kit_rel: str, script: str
    ) -> None:
        text = _read(_REPO_ROOT / kit_rel / script)
        assert "kit_sync.py" in text
        for marker in _LOGIC_MARKERS:
            assert marker not in text, (
                f"{kit_rel}/{script} still owns decision logic ({marker!r}); "
                "move it into tools/skills/_kit/"
            )
