"""Tests for hve.mdq_enforcement and settings_store target_folders helpers."""
from __future__ import annotations

import hashlib

import pytest

from hve import mdq_enforcement
from hve.gui import settings_store


class TestParseTargetFolders:
    def test_empty(self) -> None:
        assert settings_store.parse_target_folders("") == []
        assert settings_store.parse_target_folders(";;;") == []

    def test_basic(self) -> None:
        assert settings_store.parse_target_folders("docs;users-guide") == [
            "docs",
            "users-guide",
        ]

    def test_dedup_and_normalize(self) -> None:
        result = settings_store.parse_target_folders(
            "docs/;docs;docs\\sub;users-guide/;"
        )
        assert result == ["docs", "docs/sub", "users-guide"]

    def test_strip_quotes_and_whitespace(self) -> None:
        result = settings_store.parse_target_folders(' "docs" ; \'users-guide\' ')
        assert result == ["docs", "users-guide"]

    def test_dot_excluded(self) -> None:
        assert settings_store.parse_target_folders(".;./;docs") == ["docs"]


class TestSerializeTargetFolders:
    def test_roundtrip(self) -> None:
        original = ["docs", "users-guide", "qa"]
        s = settings_store.serialize_target_folders(original)
        assert settings_store.parse_target_folders(s) == original

    def test_dedup(self) -> None:
        s = settings_store.serialize_target_folders(["docs", "docs", "qa"])
        assert s == "docs;qa"


class TestSaveLoadIntegration:
    def test_target_folders_persisted(self, tmp_path, monkeypatch) -> None:
        fake = tmp_path / ".settings.txt"
        monkeypatch.setattr(settings_store, "settings_path", lambda: fake)
        cur = settings_store.load()
        cur["mdq"]["target_folders"] = settings_store.serialize_target_folders(
            ["docs", "users-guide"]
        )
        settings_store.save(cur)
        reloaded = settings_store.load()
        assert (
            settings_store.parse_target_folders(reloaded["mdq"]["target_folders"])
            == ["docs", "users-guide"]
        )
        assert settings_store.get_mdq_target_folders(settings=reloaded) == [
            "docs",
            "users-guide",
        ]

    def test_default_empty(self, tmp_path, monkeypatch) -> None:
        fake = tmp_path / ".settings.txt"
        monkeypatch.setattr(settings_store, "settings_path", lambda: fake)
        assert settings_store.get_mdq_target_folders() == []


class TestBuildEnforcementPrompt:
    def test_empty_returns_none(self) -> None:
        assert mdq_enforcement.build_enforcement_prompt([]) is None
        assert mdq_enforcement.build_enforcement_prompt(None) is None  # type: ignore[arg-type]
        assert mdq_enforcement.build_enforcement_prompt(["", "  "]) is None

    def test_non_empty_returns_block(self) -> None:
        block = mdq_enforcement.build_enforcement_prompt(["docs", "users-guide"])
        assert block is not None
        assert "python -m mdq search" in block
        assert "`docs`" in block
        assert "`users-guide`" in block
        # 強制トーンであることを確認
        assert "必ず" in block

    def test_representative_output_is_exact(self) -> None:
        block = mdq_enforcement.build_enforcement_prompt(["docs", "users-guide"])
        assert block == "\n".join(
            [
                "# Markdown-Query Skill 強制利用ルール (GUI 設定由来)",
                "以下のフォルダ配下の Markdown ファイル (.md) を参照する必要が生じた場合は、`read_file` や `grep_search` を使う前に、必ず `markdown-query` Skill (`python -m mdq search --q \"<キーワード>\" --top-k 5 --max-tokens 800`) を最優先で使用すること。",
                "",
                "対象フォルダ:",
                "  - `docs`",
                "  - `users-guide`",
                "",
                "例外:",
                "  - `python -m mdq search` のヒットが 0 件のとき、または対象が `.md` 以外のときに限り、`grep_search` / `read_file` へフォールバックしてよい。",
                "  - 索引未生成・索引が古いと判定された場合は `python -m mdq index` を実行してから再検索する。",
            ]
        ) + "\n"
        assert hashlib.sha256(block.encode("utf-8")).hexdigest() == (
            "822ed729b127d58d75a6da7689e79cf7aa323130f7e8fb881859c9e1476bf375"
        )


class TestOrchestratorInjection:
    """FR-CLI-85: Markdown-Query 強制ブロックの注入点は orchestrator の 1 箇所。"""

    def test_combines_when_configured(self, tmp_path, monkeypatch) -> None:
        from hve import mdq_enforcement

        fake = tmp_path / ".settings.txt"
        monkeypatch.setattr(settings_store, "settings_path", lambda: fake)
        cur = settings_store.load()
        cur["mdq"]["target_folders"] = "docs;qa"
        settings_store.save(cur)

        block = mdq_enforcement.build_enforcement_prompt(
            settings_store.get_mdq_target_folders()
        )
        assert block is not None
        assert "python -m mdq search" in block

    def test_passes_through_when_empty(self, tmp_path, monkeypatch) -> None:
        from hve import mdq_enforcement

        fake = tmp_path / ".settings.txt"
        monkeypatch.setattr(settings_store, "settings_path", lambda: fake)
        # 空設定: ファイル無し → get_mdq_target_folders == []
        assert settings_store.get_mdq_target_folders() == []
        assert mdq_enforcement.build_enforcement_prompt([]) is None

    def test_runner_no_longer_owns_mdq_injection(self) -> None:
        """FR-CLI-85: runner.py から Markdown-Query 前置ヘルパーが除去されていること。"""
        from pathlib import Path

        src = (Path(__file__).resolve().parents[1] / "runner.py").read_text(encoding="utf-8")
        assert "_combine_additional_prompt_with_mdq" not in src


class TestNoDuplicateInjection:
    """FR-CLI-85: `additional_prompt` / markdown-query 強制ブロックの重複前置禁止。

    Orchestrator (`_build_step_prompt`) が Step プロンプト末尾へ既に連結しているため、
    Runner が同じ値を再度前置してはならない。
    """

    @staticmethod
    def _runner_source() -> str:
        from pathlib import Path

        return (Path(__file__).resolve().parents[1] / "runner.py").read_text(encoding="utf-8")

    def test_runner_does_not_prepend_additional_prompt(self) -> None:
        """Runner の Phase 1 prefix 組み立てに additional_prompt 由来の suffix が無いこと。"""
        src = self._runner_source()
        assert "_prompt_prefix_parts.append(_additional_suffix)" not in src

    def test_runner_does_not_build_additional_suffix(self) -> None:
        """Runner が `_additional_suffix` を組み立てないこと。"""
        src = self._runner_source()
        assert "_additional_suffix" not in src

    def test_orchestrator_remains_the_single_injection_point(self) -> None:
        """Orchestrator 側の末尾連結は維持されること（唯一の注入点）。"""
        from pathlib import Path

        src = (
            Path(__file__).resolve().parents[1] / "orchestrator.py"
        ).read_text(encoding="utf-8")
        assert 'prompt = prompt + "\\n\\n" + additional_prompt' in src

    def test_mdq_block_appears_once_in_final_prompt(self, tmp_path, monkeypatch) -> None:
        """markdown-query 強制ブロックが最終プロンプトへ 1 回しか現れないこと。

        Orchestrator が末尾へ連結した後、Runner が prefix へ再度加えると 2 回になる。
        """
        from types import SimpleNamespace

        from hve import mdq_enforcement, orchestrator

        fake = tmp_path / ".settings.txt"
        monkeypatch.setattr(settings_store, "settings_path", lambda: fake)
        cur = settings_store.load()
        cur["mdq"]["target_folders"] = "docs;qa"
        settings_store.save(cur)

        block = mdq_enforcement.build_enforcement_prompt(["docs", "qa"])
        assert block is not None
        marker = "python -m mdq search"

        step = SimpleNamespace(id="1", title="T", body_template_path=None)
        step_prompt = orchestrator._build_step_prompt(
            step=step,
            params={},
            root_issue_num=None,
            render_template_fn=lambda **_: "",
            wf=None,
            additional_prompt=block,
        )
        assert step_prompt.count(marker) == block.count(marker)

        # Runner が同じ強制ブロックを prefix へ再度加えていないことをソースで確認する。
        src = self._runner_source()
        assert "_combine_additional_prompt_with_mdq(self.config.additional_prompt)" not in src

    def test_additional_prompt_appears_once_in_final_prompt(self) -> None:
        """`additional_prompt` 由来ブロックが最終プロンプトへ 1 回しか現れないこと。

        Runner は受け取った prompt をそのまま body として使い、
        `config.additional_prompt` を prefix へ再度加えてはならない。
        """
        src = self._runner_source()
        prefix_block_start = src.find("_prompt_prefix_parts: List[str] = []")
        assert prefix_block_start > 0
        prefix_block_end = src.find("_agent_prefix =", prefix_block_start)
        assert prefix_block_end > prefix_block_start
        prefix_block = src[prefix_block_start:prefix_block_end]
        code_lines = [
            line for line in prefix_block.splitlines() if not line.lstrip().startswith("#")
        ]
        code = "\n".join(code_lines)
        assert "additional_prompt" not in code
        assert "_additional_suffix" not in code
