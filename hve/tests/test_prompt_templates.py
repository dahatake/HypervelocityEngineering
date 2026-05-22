"""hve.prompt_templates の 9 区分ビルダ関数スナップショットテスト。

R3.2（`work/Issue-orchestration-refactor/remaining/R03/`）で導入。
各 build_*() 関数の出力が期待するキーフレーズを含むことを最小限検証する。
完全な文字列等価ではなく「キーフレーズ存在」で検証することで、将来の
ボイラープレート微調整に対する保守性を確保する。
"""
from __future__ import annotations

import pytest

from hve.prompt_templates import (
    build_system_role,
    build_input_files,
    build_task_scope,
    build_clarification,
    build_planning,
    build_implementation,
    build_verification,
    build_completion_report,
    build_error_recovery,
)


class TestSystemRole:
    def test_role_only(self) -> None:
        out = build_system_role(role="敵対的レビュアー")
        assert "敵対的レビュアー" in out
        assert "として振る舞ってください" in out

    def test_role_and_expertise(self) -> None:
        out = build_system_role(role="KnowledgeManager", expertise="ドメイン知識管理")
        assert "KnowledgeManager" in out
        assert "ドメイン知識管理" in out


class TestInputFiles:
    def test_empty(self) -> None:
        out = build_input_files()
        assert "入力ファイル" in out
        assert "指定なし" in out

    def test_required_and_recommended(self) -> None:
        out = build_input_files(
            required_files=["docs/A.md", "docs/B.md"],
            recommended_files=["docs/C.md"],
        )
        assert "必読" in out and "推奨" in out
        assert "docs/A.md" in out and "docs/C.md" in out


class TestTaskScope:
    def test_default(self) -> None:
        out = build_task_scope()
        assert "タスクスコープ" in out
        assert "HTML コメント" in out


class TestClarification:
    def test_default_categories(self) -> None:
        out = build_clarification()
        assert "不明点" in out
        assert "推論で進めて TBD 明記" in out
        assert "目的・スコープ" in out

    def test_custom_categories(self) -> None:
        out = build_clarification(question_categories=["セキュリティ"])
        assert "セキュリティ" in out


class TestPlanning:
    def test_default(self) -> None:
        out = build_planning()
        assert "DAG" in out
        assert "plan.md 冒頭 5 行" in out


class TestImplementation:
    def test_default_forbidden(self) -> None:
        out = build_implementation()
        assert "実装規約" in out
        assert "最小差分" in out
        assert "捏造" in out

    def test_custom_forbidden(self) -> None:
        out = build_implementation(forbidden_actions=["X 操作"])
        assert "X 操作" in out


class TestVerification:
    def test_default_marker(self) -> None:
        out = build_verification()
        assert "<!-- validation-confirmed -->" in out
        assert "検証要件" in out

    def test_custom_marker(self) -> None:
        out = build_verification(verification_marker="<!-- custom-marker -->")
        assert "<!-- custom-marker -->" in out


class TestCompletionReport:
    def test_default_sections(self) -> None:
        out = build_completion_report()
        for sec in ["目的", "変更点", "影響範囲", "検証結果", "既知の制約", "次にやるサブタスク"]:
            assert sec in out
        assert "completion-report.md" in out


class TestErrorRecovery:
    def test_default(self) -> None:
        out = build_error_recovery()
        assert "エラー時のリカバリ" in out
        assert "最大 3 回" in out


class TestPublicApi:
    """__all__ に 9 ビルダ全てが含まれることを確認。"""

    def test_all_exports(self) -> None:
        from hve import prompt_templates
        expected = {
            "build_system_role", "build_input_files", "build_task_scope",
            "build_clarification", "build_planning", "build_implementation",
            "build_verification", "build_completion_report", "build_error_recovery",
        }
        assert expected == set(prompt_templates.__all__)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
