"""Durable execution resume dialog.

The dialog is a presentation boundary only.  Candidate discovery and every
resume decision are delegated to the shared ``ResumeService`` so the GUI does
not duplicate risk, output, lease, or CAS rules.
"""

from __future__ import annotations

from typing import Any, Mapping, Optional

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QVBoxLayout,
    QWidget,
)

from ..run_state_store import DurableStateError

__all__ = ["ResumeDialog"]


def _field(record: Any, name: str, default: Any = None) -> Any:
    """Read a candidate field without assigning domain meaning to it."""

    if isinstance(record, Mapping):
        return record.get(name, default)
    return getattr(record, name, default)


def _display(value: Any) -> str:
    return "-" if value is None else str(value)


class ResumeDialog(QDialog):
    """Show shared-service resume candidates and return one approved plan."""

    def __init__(
        self,
        service: Any,
        *,
        current_head: str | None = None,
        parent: Optional[QWidget] = None,
    ) -> None:
        super().__init__(parent)
        self._service = service
        self._current_head = current_head
        self._candidates: tuple[Any, ...] = ()
        self._current_plan: Any = None
        self._accepted_plan: Any = None
        self._replay_values: dict[str, str] = {}
        self._accepted_replay_values: dict[str, str] = {}
        self._replay_edits: dict[str, QLineEdit] = {}

        self.setWindowTitle(self.tr("実行を再開"))
        self.setModal(True)
        self.resize(820, 560)

        outer = QVBoxLayout(self)
        outer.setContentsMargins(10, 10, 10, 10)
        outer.setSpacing(8)

        intro = QLabel(
            self.tr(
                "保存済みの HVE execution を選び、現在の状態から再開します。"
                "内容を確認してから実行してください。"
            )
        )
        intro.setWordWrap(True)
        intro.setProperty("hveRole", "description")
        outer.addWidget(intro)

        self.candidate_count_label = QLabel("")
        outer.addWidget(self.candidate_count_label)

        self.candidate_list = QListWidget()
        self.candidate_list.setObjectName("resumeCandidateList")
        self.candidate_list.setMinimumHeight(130)
        self.candidate_list.currentRowChanged.connect(
            self._on_candidate_changed
        )
        outer.addWidget(self.candidate_list)

        plan_box = QGroupBox(self.tr("再開プラン"))
        plan_layout = QVBoxLayout(plan_box)

        action_row = QHBoxLayout()
        action_label = QLabel(self.tr("Recovery action"))
        self.action_combo = QComboBox()
        self.action_combo.setObjectName("resumeRecoveryAction")
        action_label.setBuddy(self.action_combo)
        self.action_combo.addItem(self.tr("選択してください"), None)
        self.action_combo.addItem(
            self.tr("Reuse session"), "reuse-session"
        )
        self.action_combo.addItem(
            self.tr("Restart step"), "restart-step"
        )
        self.action_combo.currentIndexChanged.connect(
            self._on_action_changed
        )
        action_row.addWidget(action_label)
        action_row.addWidget(self.action_combo, stretch=1)
        plan_layout.addLayout(action_row)

        self.risk_label = QLabel(self.tr("Risk: -"))
        self.risk_label.setTextFormat(Qt.TextFormat.PlainText)
        self.risk_label.setWordWrap(True)
        plan_layout.addWidget(self.risk_label)

        self.missing_summary_label = QLabel(
            self.tr("Missing replay keys: -")
        )
        self.missing_summary_label.setTextFormat(Qt.TextFormat.PlainText)
        self.missing_summary_label.setWordWrap(True)
        plan_layout.addWidget(self.missing_summary_label)

        self._replay_container = QWidget()
        self._replay_layout = QVBoxLayout(self._replay_container)
        self._replay_layout.setContentsMargins(0, 0, 0, 0)
        self._replay_layout.setSpacing(4)
        plan_layout.addWidget(self._replay_container)
        outer.addWidget(plan_box, stretch=1)

        self.error_label = QLabel("")
        self.error_label.setObjectName("resumeErrorLabel")
        self.error_label.setTextFormat(Qt.TextFormat.PlainText)
        self.error_label.setWordWrap(True)
        self.error_label.setProperty("hveRole", "error")
        outer.addWidget(self.error_label)

        self.buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok
            | QDialogButtonBox.StandardButton.Cancel
        )
        self.buttons.accepted.connect(self._accept_selected)
        self.buttons.rejected.connect(self.reject)
        self._confirm_button = self.buttons.button(
            QDialogButtonBox.StandardButton.Ok
        )
        self._confirm_button.setText(self.tr("再開"))
        self._confirm_button.setObjectName("resumeConfirmButton")
        self._confirm_button.setEnabled(False)
        outer.addWidget(self.buttons)

        self._load_candidates_once()

    def selected_plan(self) -> Any:
        """Return the plan approved by the user, or ``None``."""

        return self._accepted_plan

    def selected_replay_values(self) -> dict[str, str]:
        """Return a copy of transient values approved separately from the plan."""

        return dict(self._accepted_replay_values)

    def clear_transient_state(self) -> None:
        """Drop approved plan/replay plaintext after the Workbench has launched."""

        self._current_plan = None
        self._accepted_plan = None
        self._replay_values.clear()
        self._accepted_replay_values.clear()
        for edit in self._replay_edits.values():
            edit.clear()

    def _load_candidates_once(self) -> None:
        """Load the repository-scoped candidate snapshot exactly once."""

        try:
            self._candidates = tuple(self._service.list_candidates())
        except DurableStateError as exc:
            self.candidate_count_label.setText(
                self.tr("再開候補を取得できませんでした。")
            )
            self._show_error(exc)
            return

        count = len(self._candidates)
        self.candidate_count_label.setText(
            self.tr("再開候補: {count} 件").format(count=count)
        )
        if not self._candidates:
            self.candidate_count_label.setText(
                self.tr("再開候補は 0 件です。")
            )
            self.action_combo.setEnabled(False)
            return

        previous = self.candidate_list.blockSignals(True)
        try:
            for candidate in self._candidates:
                self.candidate_list.addItem(self._candidate_text(candidate))
            self.candidate_list.setCurrentRow(0)
        finally:
            self.candidate_list.blockSignals(previous)
        self._on_candidate_changed(0)

    def _candidate_text(self, candidate: Any) -> str:
        heartbeat = _display(_field(candidate, "heartbeat_at"))
        heartbeat_age = _field(candidate, "heartbeat_age_seconds")
        if heartbeat_age is not None:
            heartbeat = self.tr("{value} (age {age}s)").format(
                value=heartbeat,
                age=_display(heartbeat_age),
            )
        return self.tr(
            "Execution: {execution} | Workflow: {workflow} | Instance: {instance} | "
            "Status: {status} | State version: {version} | Heartbeat: {heartbeat}"
        ).format(
            execution=_display(_field(candidate, "execution_id")),
            workflow=_display(_field(candidate, "workflow_id")),
            instance=_display(_field(candidate, "instance_id")),
            status=_display(_field(candidate, "status")),
            version=_display(_field(candidate, "state_version")),
            heartbeat=heartbeat,
        )

    def _on_candidate_changed(self, row: int) -> None:
        self._current_plan = None
        self._accepted_plan = None
        self._accepted_replay_values = {}
        self._replay_values = {}
        self._clear_replay_inputs()
        self.error_label.clear()
        self.risk_label.setText(self.tr("Risk: -"))
        self.missing_summary_label.setText(
            self.tr("Missing replay keys: -")
        )
        previous = self.action_combo.blockSignals(True)
        try:
            self.action_combo.setCurrentIndex(0)
        finally:
            self.action_combo.blockSignals(previous)
        self.action_combo.setEnabled(False)
        self._confirm_button.setEnabled(False)
        if 0 <= row < len(self._candidates):
            self._rebuild_plan()

    def _on_action_changed(self, _index: int) -> None:
        if self._current_candidate() is not None:
            self._rebuild_plan()

    def _on_replay_finished(self, key: str, edit: QLineEdit) -> None:
        if self._replay_edits.get(key) is not edit:
            return
        value = edit.text()
        if value.strip():
            self._replay_values[key] = value
        else:
            self._replay_values.pop(key, None)
        self._rebuild_plan()

    def _current_candidate(self) -> Any:
        row = self.candidate_list.currentRow()
        if 0 <= row < len(self._candidates):
            return self._candidates[row]
        return None

    def _rebuild_plan(self) -> None:
        """Ask the common service for one new snapshot; never retry it."""

        candidate = self._current_candidate()
        if candidate is None:
            self._current_plan = None
            self._confirm_button.setEnabled(False)
            return

        action_data = self.action_combo.currentData()
        action = str(action_data) if action_data else None
        replay_values = (
            dict(self._replay_values) if self._replay_values else None
        )
        self._current_plan = None
        self._accepted_plan = None
        self._accepted_replay_values = {}
        self._confirm_button.setEnabled(False)
        self.error_label.clear()
        try:
            plan = self._service.build_plan(
                str(_field(candidate, "execution_id")),
                action=action,
                replay_values=replay_values,
                current_head=self._current_head,
            )
        except DurableStateError as exc:
            self._show_error(exc)
            return

        self._current_plan = plan
        self._render_plan(plan)
        self._update_confirm_state()

    def _render_plan(self, plan: Any) -> None:
        risk_reasons = tuple(getattr(plan, "risk_reasons", ()) or ())
        missing_keys = tuple(
            str(key)
            for key in (getattr(plan, "missing_replay_keys", ()) or ())
        )
        self.risk_label.setText(
            self.tr("Risk: {reasons}").format(
                reasons=", ".join(str(reason) for reason in risk_reasons)
                if risk_reasons
                else self.tr("none")
            )
        )
        self.missing_summary_label.setText(
            self.tr("Missing replay keys: {keys}").format(
                keys=", ".join(missing_keys)
                if missing_keys
                else self.tr("none")
            )
        )
        self.action_combo.setEnabled(bool(risk_reasons))
        self._ensure_replay_inputs(missing_keys)

    def _ensure_replay_inputs(self, missing_keys: tuple[str, ...]) -> None:
        for key in missing_keys:
            if key in self._replay_edits:
                continue
            row = QWidget(self._replay_container)
            layout = QHBoxLayout(row)
            layout.setContentsMargins(0, 0, 0, 0)
            label = QLabel(key)
            label.setTextFormat(Qt.TextFormat.PlainText)
            edit = QLineEdit()
            edit.setObjectName(f"resumeReplay_{key}")
            edit.setAccessibleName(key)
            edit.setPlaceholderText(key)
            edit.setClearButtonEnabled(True)
            label.setBuddy(edit)
            edit.editingFinished.connect(
                lambda key=key, edit=edit: self._on_replay_finished(
                    key, edit
                )
            )
            layout.addWidget(label)
            layout.addWidget(edit, stretch=1)
            self._replay_layout.addWidget(row)
            self._replay_edits[key] = edit

    def _clear_replay_inputs(self) -> None:
        for edit in self._replay_edits.values():
            edit.clear()
        self._replay_edits.clear()
        while self._replay_layout.count():
            item = self._replay_layout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.setParent(None)
                widget.deleteLater()

    def _update_confirm_state(self) -> None:
        plan = self._current_plan
        if plan is None:
            self._confirm_button.setEnabled(False)
            return
        risks = tuple(getattr(plan, "risk_reasons", ()) or ())
        missing = tuple(getattr(plan, "missing_replay_keys", ()) or ())
        action = getattr(plan, "action", None)
        self._confirm_button.setEnabled(
            not missing and (not risks or action is not None)
        )

    def _show_error(self, error: DurableStateError) -> None:
        self._current_plan = None
        self._accepted_plan = None
        self._accepted_replay_values = {}
        self._confirm_button.setEnabled(False)
        self.error_label.setText(
            self.tr("再開プランを作成できません: {message}").format(
                message=str(error)
            )
        )

    def _accept_selected(self) -> None:
        if not self._confirm_button.isEnabled() or self._current_plan is None:
            return
        self._accepted_plan = self._current_plan
        self._accepted_replay_values = dict(self._replay_values)
        self.accept()