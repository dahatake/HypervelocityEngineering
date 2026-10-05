"""Step 1 right-pane editor for run-scoped Step input documents (FR-INPUT-04)."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Iterable, Optional, Sequence

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QCheckBox,
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from ..step_inputs import (
    STEP_INPUT_MCP_CONSENT_PROMPT,
    StepInputError,
    StepInputSlot,
    StepInputSpec,
    existing_step_input_files,
    find_docs_original_candidates,
    load_step_input_slots,
    resolve_step_input_step_ids,
)
from ..workflow_registry import get_workflow
from .doc_convert import is_supported, safe_filename, supported_extensions


@dataclass(frozen=True)
class StepInputRowView:
    workflow_id: str
    step_id: str
    required_text: str
    canonical: str
    kind: str
    exists: bool
    existing_names: tuple[str, ...]
    substitute_enabled: bool


@dataclass
class _RowWidgets:
    files: QListWidget
    substitute_button: Optional[QPushButton]


class StepInputPane(QWidget):
    """Display Step I/O contracts and collect non-persistent document choices."""

    changed = Signal()

    def __init__(
        self,
        parent: Optional[QWidget] = None,
        *,
        repo_root: Optional[Path] = None,
    ) -> None:
        super().__init__(parent)
        self._repo_root = Path(repo_root or Path.cwd())
        self._selected_steps: Dict[str, list[str]] = {}
        self._rows: list[StepInputRowView] = []
        self._selections: list[tuple[str, StepInputSpec]] = []
        self._row_widgets: Dict[tuple[str, str, Optional[str], str], _RowWidgets] = {}
        self._setup_ui()

    def _setup_ui(self) -> None:
        root_layout = QVBoxLayout(self)
        root_layout.setContentsMargins(0, 0, 0, 0)
        root_layout.setSpacing(6)

        intro = QLabel(
            self.tr(
                "選択Stepのrequired/optional入力を確認し、追加資料または欠損文書の代替を複数指定できます。"
                " PDF/Word/Excel/PowerPoint等は実行時に既存Microsoft MarkItDown経路でMarkdown化します。"
            )
        )
        intro.setWordWrap(True)
        intro.setProperty("hveRole", "description")
        root_layout.addWidget(intro)

        candidate_row = QHBoxLayout()
        self._candidate_query = QLineEdit()
        self._candidate_query.setPlaceholderText(
            self.tr("docs-original/ の候補を検索（空でも一覧表示）")
        )
        self._candidate_search = QPushButton(self.tr("候補検索"))
        self._candidate_search.clicked.connect(self._refresh_candidates)
        candidate_row.addWidget(self._candidate_query, stretch=1)
        candidate_row.addWidget(self._candidate_search)
        root_layout.addLayout(candidate_row)

        self._candidate_list = QListWidget()
        self._candidate_list.setSelectionMode(
            QListWidget.SelectionMode.ExtendedSelection
        )
        self._candidate_list.setMaximumHeight(100)
        root_layout.addWidget(self._candidate_list)
        self._candidate_status = QLabel("")
        self._candidate_status.setWordWrap(True)
        self._candidate_status.setProperty("hveRole", "muted")
        root_layout.addWidget(self._candidate_status)
        self._candidate_add = QPushButton(self.tr("選択候補を先頭の実行Stepへ追加"))
        self._candidate_add.clicked.connect(self._add_selected_candidates)
        root_layout.addWidget(self._candidate_add)

        self._mcp_consent = QCheckBox(STEP_INPUT_MCP_CONSENT_PROMPT)
        self._mcp_consent.setToolTip(
            self.tr(
                "質問が1件以上あり、知識源が利用できる場合だけ知識探索で調べます。"
            )
        )
        root_layout.addWidget(self._mcp_consent)

        self._content = QWidget()
        self._content_layout = QVBoxLayout(self._content)
        self._content_layout.setContentsMargins(0, 0, 0, 0)
        self._content_layout.setSpacing(8)
        self._placeholder = QLabel(self.tr("（Workflow / Stepを選択してください）"))
        self._placeholder.setProperty("hveRole", "muted")
        self._content_layout.addWidget(self._placeholder)
        self._content_layout.addStretch(1)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setWidget(self._content)
        root_layout.addWidget(scroll, stretch=1)

    def set_repo_root(self, repo_root: Path) -> None:
        self._repo_root = Path(repo_root)
        self.set_selected_steps(self._selected_steps)

    def set_selected_steps(
        self, steps_by_workflow: Optional[Dict[str, Sequence[str]]] = None
    ) -> None:
        selected: Dict[str, list[str]] = {}
        for workflow_id, step_ids in (steps_by_workflow or {}).items():
            workflow = get_workflow(workflow_id)
            if workflow is None:
                continue
            try:
                effective = resolve_step_input_step_ids(workflow.id, step_ids)
            except StepInputError:
                continue
            selected[workflow.id] = list(effective)
        self._selected_steps = selected
        active = {
            (workflow_id, step_id)
            for workflow_id, step_ids in selected.items()
            for step_id in step_ids
        }
        self._selections = [
            item for item in self._selections
            if (item[0], item[1].step_id) in active
        ]
        self._rebuild()

    def _clear_content(self) -> None:
        while self._content_layout.count():
            item = self._content_layout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.setParent(None)
                widget.deleteLater()
        self._row_widgets.clear()
        self._rows.clear()

    def _rebuild(self) -> None:
        self._clear_content()
        for workflow_id, step_ids in self._selected_steps.items():
            workflow = get_workflow(workflow_id)
            if workflow is None:
                continue
            for step_id in step_ids:
                step = workflow.get_step(step_id)
                if step is None or step.is_container:
                    continue
                try:
                    slots = load_step_input_slots(
                        self._repo_root, workflow_id, step_id
                    )
                except StepInputError as exc:
                    error = QLabel(f"{workflow_id} Step.{step_id}: {exc}")
                    error.setWordWrap(True)
                    error.setProperty("hveRole", "error")
                    self._content_layout.addWidget(error)
                    continue
                for slot in slots:
                    self._add_slot_row(slot)
                self._add_generic_row(workflow_id, step_id)
        if not self._row_widgets:
            self._content_layout.addWidget(
                QLabel(self.tr("（選択された実行Stepに表示可能な文書入力がありません）"))
            )
        self._content_layout.addStretch(1)
        self._refresh_all_file_lists()

    def _existing_names(self, canonical: str) -> tuple[str, ...]:
        return existing_step_input_files(self._repo_root, canonical)

    def _add_slot_row(self, slot: StepInputSlot) -> None:
        existing_names = self._existing_names(slot.canonical)
        exists = bool(existing_names)
        view = StepInputRowView(
            workflow_id=slot.workflow_id,
            step_id=slot.step_id,
            required_text="required" if slot.required else "optional",
            canonical=slot.canonical,
            kind=slot.kind,
            exists=exists,
            existing_names=existing_names,
            substitute_enabled=slot.substitutable and not exists,
        )
        self._rows.append(view)
        frame = self._build_row_frame(
            workflow_id=slot.workflow_id,
            step_id=slot.step_id,
            canonical=slot.canonical,
            title=(
                f"{slot.workflow_id} Step.{slot.step_id} — "
                f"{'required' if slot.required else 'optional'} / {slot.kind}"
            ),
            details=(
                f"canonical: {slot.canonical}\n"
                f"status: {'existing — ' + ', '.join(existing_names) if exists else 'missing'}"
            ),
            allow_substitute=view.substitute_enabled,
        )
        self._content_layout.addWidget(frame)

    def _add_generic_row(self, workflow_id: str, step_id: str) -> None:
        frame = self._build_row_frame(
            workflow_id=workflow_id,
            step_id=step_id,
            canonical=None,
            title=f"{workflow_id} Step.{step_id} — additional documents",
            details=self.tr("このStepだけへ追加する任意資料（0件以上・複数選択可）"),
            allow_substitute=False,
        )
        self._content_layout.addWidget(frame)

    def _build_row_frame(
        self,
        *,
        workflow_id: str,
        step_id: str,
        canonical: Optional[str],
        title: str,
        details: str,
        allow_substitute: bool,
    ) -> QFrame:
        frame = QFrame()
        frame.setFrameShape(QFrame.Shape.StyledPanel)
        layout = QVBoxLayout(frame)
        layout.setContentsMargins(8, 6, 8, 6)
        heading = QLabel(f"<b>{title}</b>")
        layout.addWidget(heading)
        detail = QLabel(details)
        detail.setWordWrap(True)
        detail.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        layout.addWidget(detail)

        buttons = QHBoxLayout()
        add_button = QPushButton(self.tr("追加資料を選択…"))
        add_button.clicked.connect(
            lambda _checked=False, w=workflow_id, s=step_id, c=canonical:
            self._choose_files(w, s, c, "additional")
        )
        buttons.addWidget(add_button)
        substitute_button: Optional[QPushButton] = None
        if allow_substitute:
            substitute_button = QPushButton(self.tr("代替資料を選択…"))
            substitute_button.clicked.connect(
                lambda _checked=False, w=workflow_id, s=step_id, c=canonical:
                self._choose_files(w, s, c, "substitute")
            )
            buttons.addWidget(substitute_button)
        buttons.addStretch(1)
        layout.addLayout(buttons)

        files = QListWidget()
        files.setMaximumHeight(74)
        layout.addWidget(files)
        for role in ("additional", "substitute"):
            self._row_widgets[(workflow_id, step_id, canonical, role)] = _RowWidgets(
                files=files,
                substitute_button=substitute_button,
            )
        return frame

    def _choose_files(
        self,
        workflow_id: str,
        step_id: str,
        canonical: Optional[str],
        role: str,
    ) -> None:
        patterns = " ".join(f"*{ext}" for ext in supported_extensions())
        names, _filter = QFileDialog.getOpenFileNames(
            self,
            self.tr("Step入力文書を選択"),
            str(self._repo_root),
            self.tr("対応文書 ({patterns});;すべてのファイル (*)").format(
                patterns=patterns
            ),
        )
        if names:
            try:
                self.set_files(
                    workflow_id,
                    step_id,
                    canonical,
                    role,
                    [Path(name) for name in names],
                )
            except StepInputError as exc:
                self._candidate_status.setText(str(exc))

    def set_files(
        self,
        workflow_id: str,
        step_id: str,
        canonical: Optional[str],
        role: str,
        files: Iterable[Path],
    ) -> None:
        selected_files = [Path(path) for path in files]
        for path in selected_files:
            if path.is_symlink() or not path.is_file():
                raise StepInputError(
                    f"Step入力sourceは安全な通常ファイルでなければなりません: {path}"
                )
            if not is_supported(path):
                raise StepInputError(
                    f"Step入力sourceは対応文書形式ではありません: {path.suffix}"
                )
        key = (workflow_id, step_id, canonical, role)
        self._selections = [
            item for item in self._selections
            if (item[0], item[1].step_id, item[1].canonical, item[1].role) != key
        ]
        for path in selected_files:
            self._selections.append(
                (
                    workflow_id,
                    StepInputSpec(
                        step_id=step_id,
                        role=role,
                        canonical=canonical,
                        source=Path(path),
                    ),
                )
            )
        self._refresh_all_file_lists()
        self.changed.emit()

    def _refresh_all_file_lists(self) -> None:
        unique_lists = {id(value.files): value.files for value in self._row_widgets.values()}
        for widget in unique_lists.values():
            widget.clear()
        for workflow_id, spec in self._selections:
            key = (workflow_id, spec.step_id, spec.canonical, spec.role)
            widgets = self._row_widgets.get(key)
            if widgets is None:
                continue
            path = Path(spec.source)
            widgets.files.addItem(f"{spec.role}: {path.name} → {safe_filename(path.name)}")

    def _refresh_candidates(self) -> None:
        result = find_docs_original_candidates(
            self._repo_root,
            self._candidate_query.text().strip(),
        )
        self._candidate_list.clear()
        for candidate in result.candidates:
            self._candidate_list.addItem(candidate.path)
        self._candidate_status.setText(
            result.warning
            or self.tr("{source}: {count}件（自動選択しません）").format(
                source=result.source,
                count=len(result.candidates),
            )
        )

    def _first_target_step(self) -> Optional[tuple[str, str]]:
        for workflow_id, step_ids in self._selected_steps.items():
            workflow = get_workflow(workflow_id)
            if workflow is None:
                continue
            for step_id in step_ids:
                step = workflow.get_step(step_id)
                if step is not None and not step.is_container:
                    return workflow_id, step_id
        return None

    def _add_selected_candidates(self) -> None:
        target = self._first_target_step()
        if target is None:
            self._candidate_status.setText(self.tr("追加先の実行Stepがありません。"))
            return
        paths = [self._repo_root / item.text() for item in self._candidate_list.selectedItems()]
        if paths:
            self.set_files(target[0], target[1], None, "additional", paths)

    def rows(self) -> tuple[StepInputRowView, ...]:
        return tuple(self._rows)

    def selections_for_workflow(self, workflow_id: str) -> tuple[StepInputSpec, ...]:
        return tuple(spec for owner, spec in self._selections if owner == workflow_id)

    def conversion_previews(self) -> tuple[str, ...]:
        return tuple(safe_filename(Path(spec.source).name) for _, spec in self._selections)

    def mcp_consent(self) -> bool:
        return self._mcp_consent.isChecked()

    def persistent_values(self) -> dict[str, object]:
        """Step入力はrun-scopedであり、settings_storeへ永続化しない。"""
        return {}
