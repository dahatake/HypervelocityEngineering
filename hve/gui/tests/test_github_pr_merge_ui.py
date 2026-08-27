"""FR-GUI-47: check-runs 表示と確認付き Pull Request merge UI 契約。"""

from __future__ import annotations

import os
from typing import Any, Callable

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
pytest.importorskip("PySide6")
from PySide6.QtWidgets import QApplication, QMessageBox  # noqa: E402

from hve.gui import github_pr_panel as module  # noqa: E402
from hve.gui.github_service import GitHubServiceError  # noqa: E402


def _pull_request(*, head_sha: str = "head123") -> dict[str, Any]:
    return {
        "number": 42,
        "title": "merge target",
        "state": "open",
        "merged": False,
        "draft": False,
        "body": "",
        "head": {
            "ref": "feature/t14",
            "sha": head_sha,
            "repo": {"full_name": "o/r"},
        },
        "base": {"ref": "main"},
        "user": {"login": "author"},
    }


def _check(
    name: str = "build",
    *,
    status: str = "completed",
    conclusion: str | None = "success",
) -> dict[str, Any]:
    return {"name": name, "status": status, "conclusion": conclusion}


@pytest.fixture(scope="module")
def qapp():
    return QApplication.instance() or QApplication([])


@pytest.fixture
def panel(qapp, monkeypatch):
    widget = module.GitHubPullRequestPanel()
    widget.set_repo("o/r")
    monkeypatch.setattr(widget, "_load_files", lambda _number: None)
    monkeypatch.setattr(widget, "_load_comments", lambda _number: None)
    monkeypatch.setattr(
        widget,
        "_request_pull_request_reviews",
        lambda *_args, **_kwargs: None,
    )
    generation = widget._pull_request_load_generation
    widget._on_pull_request_loaded(
        _pull_request(),
        repo_at_request="o/r",
        number_at_request=42,
        generation=generation,
    )

    pending: list[
        tuple[
            Callable[[], Any],
            Callable[[Any], None],
            Callable[[str], None] | None,
        ]
    ] = []
    calls: dict[str, list[Any]] = {"checks": [], "merge": []}
    state: dict[str, Any] = {
        "checks": [_check()],
        "merge": {"sha": "merged123", "merged": True, "message": "ok"},
    }

    def _list_check_runs(repo: str, ref: str) -> Any:
        calls["checks"].append((repo, ref))
        result = state["checks"]
        if isinstance(result, Exception):
            raise result
        return list(result) if isinstance(result, list) else result

    def _merge(
        repo: str,
        number: Any,
        merge_method: str,
        *,
        sha: str | None = None,
    ) -> Any:
        calls["merge"].append((repo, int(number), merge_method, sha))
        result = state["merge"]
        if isinstance(result, Exception):
            raise result
        return dict(result) if isinstance(result, dict) else result

    def _defer(
        task: Callable[[], Any],
        on_ok: Callable[[Any], None],
        on_ng: Callable[[str], None] | None = None,
    ) -> None:
        pending.append((task, on_ok, on_ng))

    monkeypatch.setattr(module.github_service, "list_check_runs", _list_check_runs)
    monkeypatch.setattr(module.github_service, "merge_pull_request", _merge)
    monkeypatch.setattr(widget, "_run", _defer)
    widget._merge_pending = pending  # type: ignore[attr-defined]
    widget._merge_calls = calls  # type: ignore[attr-defined]
    widget._merge_state = state  # type: ignore[attr-defined]
    yield widget
    widget.deleteLater()


def _resolve_success(panel, result: Any = None, *, use_task: bool = True) -> None:
    task, on_ok, _on_ng = panel._merge_pending.pop(0)
    on_ok(task() if use_task else result)


def _resolve_failure(panel, message: str) -> None:
    _task, _on_ok, on_ng = panel._merge_pending.pop(0)
    assert on_ng is not None
    on_ng(message)


def _load_checks(panel, checks: Any = None) -> None:
    if checks is not None:
        panel._merge_state["checks"] = checks
    panel.refresh_check_runs()
    _resolve_success(panel)


def _confirm(
    monkeypatch,
    answer: QMessageBox.StandardButton,
    captured: dict[str, Any] | None = None,
) -> None:
    def _question(parent, title, text, buttons, default):
        if captured is not None:
            captured.update(
                parent=parent,
                title=title,
                text=text,
                buttons=buttons,
                default=default,
            )
        return answer

    monkeypatch.setattr(module.QMessageBox, "question", _question)


def test_surface_is_present_and_merge_is_fail_closed_before_fetch(panel) -> None:
    assert panel.refresh_check_runs_button.text() == "check-runs を更新"
    assert panel.merge_button.text() == "Pull Request をマージ"
    assert [
        panel.merge_method_combo.itemData(index)
        for index in range(panel.merge_method_combo.count())
    ] == ["merge", "squash", "rebase"]
    assert panel.check_run_list.count() == 0
    assert not panel.merge_button.isEnabled()
    assert "取得" in panel.merge_guidance_label.text()


def test_explicit_refresh_uses_selected_head_and_enables_only_after_success(
    panel,
) -> None:
    panel.refresh_check_runs()

    assert panel._merge_calls["checks"] == []
    assert len(panel._merge_pending) == 1
    assert not panel.merge_button.isEnabled()

    _resolve_success(panel)

    assert panel._merge_calls["checks"] == [("o/r", "head123")]
    assert panel.check_run_list.count() == 1
    assert "build" in panel.check_run_list.item(0).text()
    assert panel.merge_button.isEnabled()


@pytest.mark.parametrize(
    "checks",
    [
        [_check(status="in_progress", conclusion=None)],
        [_check(conclusion="failure")],
        [_check(conclusion="cancelled")],
    ],
)
def test_incomplete_or_unsuccessful_check_disables_merge(panel, checks) -> None:
    _load_checks(panel, checks)

    assert not panel.merge_button.isEnabled()
    assert "マージできません" in panel.merge_guidance_label.text()


@pytest.mark.parametrize("response", [None, {}, ["invalid"], [{}]])
def test_malformed_check_response_fails_closed(panel, response: Any) -> None:
    panel.refresh_check_runs()
    _resolve_success(panel, response, use_task=False)

    assert panel.check_run_list.count() == 0
    assert not panel.merge_button.isEnabled()
    assert "解釈" in panel.status_label.text()


def test_all_allowed_conclusions_enable_merge(panel) -> None:
    _load_checks(
        panel,
        [
            _check("build", conclusion="success"),
            _check("lint", conclusion="neutral"),
            _check("optional", conclusion="skipped"),
        ],
    )

    assert panel.merge_button.isEnabled()


def test_confirmation_lists_number_branches_and_method_and_defaults_no(
    panel, monkeypatch
) -> None:
    _load_checks(panel)
    panel.merge_method_combo.setCurrentIndex(
        panel.merge_method_combo.findData("squash")
    )
    captured: dict[str, Any] = {}
    _confirm(monkeypatch, QMessageBox.StandardButton.No, captured)

    panel.merge_current_pull_request()

    assert "#42" in captured["text"]
    assert "feature/t14" in captured["text"]
    assert "main" in captured["text"]
    assert "squash" in captured["text"]
    assert captured["default"] == QMessageBox.StandardButton.No
    assert panel._merge_calls["merge"] == []
    assert panel._merge_pending == []
    assert panel.merge_method_combo.currentData() == "squash"


def test_merge_uses_frozen_repo_number_method_and_head_sha(
    panel, monkeypatch
) -> None:
    _load_checks(panel)
    panel.merge_method_combo.setCurrentIndex(
        panel.merge_method_combo.findData("rebase")
    )
    _confirm(monkeypatch, QMessageBox.StandardButton.Yes)

    panel.merge_current_pull_request()

    assert panel._merge_calls["merge"] == []
    assert len(panel._merge_pending) == 1
    assert not panel.merge_button.isEnabled()
    _resolve_success(panel)

    assert panel._merge_calls["merge"] == [
        ("o/r", 42, "rebase", "head123")
    ]
    assert panel._current is not None
    assert panel._current["merged"] is True
    assert "マージしました" in panel.status_label.text()
    assert not panel.merge_button.isEnabled()


def test_merge_in_flight_blocks_direct_refresh_review_and_comment_mutations(
    panel, monkeypatch
) -> None:
    _load_checks(panel)
    panel.new_comment_edit.set_text("must not post")
    panel.review_body_edit.set_text("must not review")
    panel._pull_requests_have_more = True
    panel._update_review_controls()
    _confirm(monkeypatch, QMessageBox.StandardButton.Yes)

    panel.merge_current_pull_request()
    pending_count = len(panel._merge_pending)
    panel.refresh_pull_requests()
    panel.load_more_pull_requests()
    panel.refresh_pull_request_reviews()
    panel.submit_review()
    panel.open_review_comment_dialog()
    panel.post_comment()
    panel.push_current_branch()

    assert len(panel._merge_pending) == pending_count == 1
    assert not panel.refresh_button.isEnabled()
    assert not panel.refresh_reviews_button.isEnabled()
    assert not panel.submit_review_button.isEnabled()
    assert not panel.post_comment_button.isEnabled()
    assert not panel.push_button.isEnabled()

    _resolve_failure(panel, "merge stopped")


def test_merge_failure_preserves_method_but_requires_fresh_checks(
    panel, monkeypatch
) -> None:
    _load_checks(panel)
    panel.merge_method_combo.setCurrentIndex(
        panel.merge_method_combo.findData("squash")
    )
    _confirm(monkeypatch, QMessageBox.StandardButton.Yes)

    panel.merge_current_pull_request()
    _resolve_failure(panel, "head が更新されたか競合しています")

    assert panel.merge_method_combo.currentData() == "squash"
    assert panel.check_run_list.count() == 0
    assert not panel.merge_button.isEnabled()
    assert "取得" in panel.merge_guidance_label.text()
    assert "head が更新" in panel.status_label.text()
    assert panel._current is not None
    assert panel._current.get("merged") is not True


@pytest.mark.parametrize("response", [None, {}, {"merged": False}, {"merged": "true"}])
def test_unconfirmed_merge_response_never_marks_merged(
    panel, monkeypatch, response: Any
) -> None:
    _load_checks(panel)
    _confirm(monkeypatch, QMessageBox.StandardButton.Yes)

    panel.merge_current_pull_request()
    _resolve_success(panel, response, use_task=False)

    assert panel._current is not None
    assert panel._current.get("merged") is not True
    assert not panel.merge_button.isEnabled()
    assert panel.check_run_list.count() == 0
    assert "解釈" in panel.status_label.text()


def test_head_change_after_check_fetch_invalidates_merge(panel) -> None:
    _load_checks(panel)
    assert panel.merge_button.isEnabled()

    assert panel._current is not None
    panel._current["head"]["sha"] = "new-head"
    panel._update_merge_controls()

    assert not panel.merge_button.isEnabled()
    assert "head" in panel.merge_guidance_label.text()


def test_target_change_during_confirmation_prevents_merge(
    panel, monkeypatch
) -> None:
    _load_checks(panel)

    def _question(*_args: Any) -> QMessageBox.StandardButton:
        assert panel._current is not None
        panel._current["head"]["sha"] = "changed-during-confirmation"
        return QMessageBox.StandardButton.Yes

    monkeypatch.setattr(module.QMessageBox, "question", _question)

    panel.merge_current_pull_request()

    assert panel._merge_pending == []
    assert panel._merge_calls["merge"] == []
    assert "変更" in panel.status_label.text()
