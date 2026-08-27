"""FR-GUI-36: rolling進捗コメントMarkdown formatterのRED契約。"""

from __future__ import annotations

import importlib
import inspect


def _module():
    return importlib.import_module("hve.gui.github_progress_format")


def _format(**overrides):
    values = {
        "run_id": "run-123",
        "workflow_id": "aas",
        "overall_status": "running",
        "steps": [
            {"step_id": "1", "status": "done", "elapsed": 1.25},
            {"step_id": "2", "status": "running", "elapsed": 0.5},
        ],
        "updated_at": "2026-08-25T12:00:00Z",
        "console_text": None,
    }
    values.update(overrides)
    return _module().format_progress_comment(**values)


class TestProgressMarkdown:
    def test_has_stable_run_marker_and_heading(self) -> None:
        text = _format()
        assert "<!-- hve-progress:run=run-123 -->" in text
        assert "### HVE 実行進捗" in text

    def test_has_metadata_and_step_table(self) -> None:
        text = _format()
        assert "| run-id | `run-123` |" in text
        assert "| workflow | `aas` |" in text
        assert "| Step | Status | Elapsed |" in text
        assert "| `1` | done | 1.25s |" in text

    def test_console_is_omitted_before_final(self) -> None:
        assert "HVE コンソール出力" not in _format(console_text=None)

    def test_interim_update_ignores_console_even_when_supplied(self) -> None:
        text = _format(overall_status="running", console_text="secret log")
        assert "HVE コンソール出力" not in text
        assert "secret log" not in text

    def test_final_console_reuses_existing_300_line_formatter(self) -> None:
        text = _format(
            overall_status="done",
            console_text="\n".join(f"line-{index}" for index in range(305)),
        )
        assert "### HVE コンソール出力" in text
        assert "先頭 5 行を省略" in text
        assert "line-304" in text
        assert "line-0\n" not in text

    def test_final_console_redacts_authorization_values(self) -> None:
        text = _format(
            overall_status="done",
            console_text="Authorization: Bearer abc.def-ghi",
        )
        assert "abc.def-ghi" not in text
        assert "[REDACTED]" in text

    def test_formatter_signature_accepts_no_secret_or_prompt_payload(self) -> None:
        names = set(inspect.signature(_module().format_progress_comment).parameters)
        assert names == {
            "run_id",
            "workflow_id",
            "overall_status",
            "steps",
            "updated_at",
            "console_text",
        }

    def test_table_values_escape_pipe_and_newline(self) -> None:
        text = _format(
            steps=[{"step_id": "1|x\ny", "status": "failed", "elapsed": 1}],
        )
        assert "1|x" not in text
        assert "1&#124;x<br>y" in text

    def test_table_values_escape_html_and_backtick(self) -> None:
        text = _format(
            steps=[{"step_id": "<img>`x`", "status": "failed", "elapsed": 1}],
        )
        assert "<img>" not in text
        assert "&lt;img&gt;&#96;x&#96;" in text

    def test_same_input_produces_same_text(self) -> None:
        assert _format() == _format()

    def test_final_output_is_deterministic(self) -> None:
        console = "\n".join(f"line-{index}" for index in range(305))
        first = _format(overall_status="done", console_text=console)
        second = _format(overall_status="done", console_text=console)
        assert first == second

    def test_missing_elapsed_is_shown_as_dash(self) -> None:
        text = _format(steps=[{"step_id": "1", "status": "running"}])
        assert "| `1` | running | - |" in text

    def test_marker_is_stable_across_updates(self) -> None:
        module = _module()
        assert module.progress_marker("run-123") in _format()
        assert module.progress_marker("run-123") in _format(overall_status="done")

    def test_marker_round_trips_for_real_run_ids(self) -> None:
        module = _module()
        for run_id in ("20260825T223137-998829", "run_1", "a.b:c/d#e@f"):
            assert module.progress_marker(run_id).endswith(f"{run_id} -->")

    def test_marker_cannot_terminate_the_html_comment_early(self) -> None:
        module = _module()
        marker = module.progress_marker("x --> <img src=1>")
        assert marker.count("-->") == 1
        assert marker.endswith(" -->")
        assert "<img" not in marker

    def test_marker_is_deterministic(self) -> None:
        module = _module()
        assert module.progress_marker("a|b\nc") == module.progress_marker("a|b\nc")


class TestFinalStatuses:
    """FR-GUI-36: console 付加は Workflow 終端状態だけに限る。"""

    def test_workflow_terminal_statuses_attach_console(self) -> None:
        for status in ("done", "failed", "cancelled"):
            text = _format(overall_status=status, console_text="tail log")
            assert "### HVE コンソール出力" in text, status

    def test_step_terminal_statuses_are_not_workflow_final(self) -> None:
        for status in ("skipped", "blocked", "running", "queued", ""):
            text = _format(overall_status=status, console_text="tail log")
            assert "### HVE コンソール出力" not in text, status
            assert "tail log" not in text, status

    def test_final_statuses_are_exported(self) -> None:
        assert _module().FINAL_STATUSES == frozenset({"done", "failed", "cancelled"})
