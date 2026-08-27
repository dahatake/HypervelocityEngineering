"""FR-GUI-39: Issue title generation wiring."""

from __future__ import annotations

import os
from typing import Any, Dict, List

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

pytest.importorskip("PySide6")
from PySide6.QtWidgets import QApplication  # noqa: E402


@pytest.fixture(scope="module")
def qapp():
    app = QApplication.instance() or QApplication([])
    yield app


@pytest.fixture
def panel(qapp, monkeypatch):
    from hve.gui import github_issue_panel as module

    generated: List[Any] = []
    created: List[Any] = []

    def _generate(kind: str, body: str, **kwargs: Any) -> str:
        generated.append((kind, body, kwargs))
        return "Generated issue title"

    monkeypatch.setattr(module, "generate_github_title", _generate, raising=False)
    monkeypatch.setattr(
        module.github_service,
        "create_issue_details",
        lambda repo, title, body, **_metadata: (
            created.append((repo, title, body))
            or {"number": 77, "id": 7700, "warnings": []}
        ),
    )
    monkeypatch.setattr(
        module.github_service,
        "list_issues",
        lambda repo, state="open", per_page=50: [],
    )

    widget = module.GitHubIssuePanel()
    widget.set_repo("o/r")

    def _sync(task, on_ok, on_ng=None):
        try:
            result = task()
        except Exception as exc:  # noqa: BLE001 - worker boundary parity
            (on_ng or widget._show_error)(str(exc))
        else:
            on_ok(result)

    monkeypatch.setattr(widget, "_run", _sync)
    widget._generated = generated  # type: ignore[attr-defined]
    widget._created = created  # type: ignore[attr-defined]
    yield widget
    widget.deleteLater()


class TestExplicitGeneration:
    def test_form_has_generate_button(self, panel) -> None:
        assert panel.generate_title_button.text() == "Copilot でタイトルを生成"

    def test_generate_fills_title_without_creating_issue(self, panel) -> None:
        panel.create_title_edit.setText("Existing title")
        panel.create_body_edit.set_text("## Problem\nLogin validation is weak.")

        panel.generate_issue_title()

        assert panel.create_title_edit.text() == "Generated issue title"
        assert panel._generated[-1][0:2] == (
            "issue",
            "## Problem\nLogin validation is weak.",
        )
        assert panel._created == []

    def test_blank_body_does_not_consume_tokens(self, panel) -> None:
        before = len(panel._generated)
        panel.create_body_edit.set_text("   ")

        panel.generate_issue_title()

        assert len(panel._generated) == before
        assert "本文" in panel.status_label.text()


class TestCreateContinuation:
    def test_blank_title_generates_then_creates(self, panel) -> None:
        panel.create_title_edit.clear()
        panel.create_body_edit.set_text("Implement safe retry behavior")

        panel.create_issue()

        assert panel._generated[-1][0:2] == (
            "issue",
            "Implement safe retry behavior",
        )
        assert panel._created[-1] == (
            "o/r",
            "Generated issue title",
            "Implement safe retry behavior",
        )
        assert panel.create_title_edit.text() == ""
        assert panel.create_body_edit.text() == ""

    def test_nonblank_title_skips_generation(self, panel) -> None:
        before = len(panel._generated)
        panel.create_title_edit.setText("User title")
        panel.create_body_edit.set_text("Body")

        panel.create_issue()

        assert len(panel._generated) == before
        assert panel._created[-1] == ("o/r", "User title", "Body")

    def test_blank_body_never_generates_or_creates(self, panel) -> None:
        generated_before = len(panel._generated)
        created_before = len(panel._created)
        panel.create_title_edit.clear()
        panel.create_body_edit.set_text("   ")

        panel.create_issue()

        assert len(panel._generated) == generated_before
        assert len(panel._created) == created_before

    def test_repo_change_during_generation_aborts_create(self, panel, monkeypatch) -> None:
        pending: Dict[str, Any] = {}

        def _delayed(task, on_ok, on_ng=None):
            pending.update(on_ok=on_ok)

        monkeypatch.setattr(panel, "_run", _delayed)
        panel.set_repo("o/r")
        panel.create_title_edit.clear()
        panel.create_body_edit.set_text("Body")
        panel.create_issue()
        panel.set_repo("other/repo")
        created_before = len(panel._created)
        pending["on_ok"]("Generated title")
        assert len(panel._created) == created_before
        assert panel.create_title_edit.text() == "Generated title"
        assert "作成しませんでした" in panel.status_label.text()


class TestFailureAndLifecycle:
    def test_generation_failure_preserves_inputs(self, panel, monkeypatch) -> None:
        from hve import github_title_generator
        from hve.gui import github_issue_panel as module

        def _fail(*_args: Any, **_kwargs: Any) -> str:
            raise github_title_generator.GitHubTitleGenerationError(
                "Copilot CLI title generation failed"
            )

        monkeypatch.setattr(module, "generate_github_title", _fail, raising=False)
        panel.create_title_edit.clear()
        panel.create_body_edit.set_text("Keep this body")
        created_before = len(panel._created)

        panel.create_issue()

        assert panel.create_title_edit.text() == ""
        assert panel.create_body_edit.text() == "Keep this body"
        assert len(panel._created) == created_before
        assert "Copilot CLI" in panel.status_label.text()
        assert panel.create_issue_button.isEnabled()
        assert panel.generate_title_button.isEnabled()

    def test_generation_disables_all_create_controls(self, panel, monkeypatch) -> None:
        pending: Dict[str, Any] = {}

        def _delayed(task, on_ok, on_ng=None):
            pending.update(task=task, on_ok=on_ok, on_ng=on_ng)

        monkeypatch.setattr(panel, "_run", _delayed)
        panel.create_body_edit.set_text("Body")

        panel.generate_issue_title()

        for widget in (
            panel.create_title_edit,
            panel.create_body_edit,
            panel.generate_title_button,
            panel.create_issue_button,
        ):
            assert not widget.isEnabled()

        pending["on_ok"]("Generated title")
        for widget in (
            panel.create_title_edit,
            panel.create_body_edit,
            panel.generate_title_button,
            panel.create_issue_button,
        ):
            assert widget.isEnabled()

    def test_shutdown_contract_keeps_title_worker_bounded(self, panel) -> None:
        assert callable(panel.shutdown)
        assert panel._workers == []
