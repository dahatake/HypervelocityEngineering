"""hve.gui.wizard — Issue Template 風の起動ウィザード（QWizard ベース）。

QWizard を使って多段ページ形式の入力 UI を提供する:

  Page 1: ワークフロー選択（workflow_registry から動的取得）
  Page 2: 共通オプション（dry-run, quiet, auto-qa など）
  Page 3: 確認（入力内容のサマリ＋コピーボタン）

ウィザード完了時、`WizardResult` を返す。これを `WorkbenchWindow` が
orchestrator サブプロセスのコマンドライン引数構築に使う。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QFormLayout,
    QLabel,
    QLineEdit,
    QPlainTextEdit,
    QVBoxLayout,
    QWidget,
    QWizard,
    QWizardPage,
)

from .workflow_display import format_workflow_label

from .copy_button import CopyButton


def _load_workflow_choices() -> List[Tuple[str, str]]:
    """workflow_registry からワークフロー一覧を取得する。

    インポートに失敗した場合（循環インポートや未インストール環境）は
    最低限のフォールバックリストを返す。
    """
    try:
        from hve.workflow_registry import list_workflows

        return [(wf.id, wf.name) for wf in list_workflows()]
    except Exception:
        # workflow_registry.WorkflowDef.name と一致させる
        return [
            ("akm", "Knowledge Management"),
            ("aqod", "Original Docs Review"),
            ("ard", "Auto Requirement Definition"),
            ("aad-web", "Web App Design"),
            ("asdw-web", "Web App Dev & Deploy"),
        ]


@dataclass
class WizardResult:
    """ウィザード完了時の入力結果。orchestrator 引数構築に使用。"""

    workflow: str = ""
    dry_run: bool = False
    quiet: bool = False
    auto_qa: bool = False
    additional_args: List[str] = field(default_factory=list)
    # --- Autopilot 追加フィールド ---
    app_id: Optional[str] = None
    autopilot_chain: List[str] = field(default_factory=list)
    autopilot_child: bool = False
    # --- Work IQ 追加フィールド（Sub-002 / Phase 1）---
    # Work IQ ページで入力された CLI 引数（`--workiq*` 系のみ）。
    # 未入力（ページ未表示・全項目空）の場合は空リスト。
    workiq_argv: List[str] = field(default_factory=list)

    def to_orchestrate_argv(self) -> List[str]:
        """`python -m hve orchestrate ...` の引数リストに変換する。"""
        argv: List[str] = ["orchestrate", "--workflow", self.workflow]
        if self.dry_run:
            argv.append("--dry-run")
        if self.quiet:
            argv.append("--quiet")
        if self.auto_qa:
            argv.append("--auto-qa")
        if self.app_id:
            argv.extend(["--app-id", self.app_id])
        # Work IQ 系オプションをスプライス（Phase 1 / Sub-002）
        if self.workiq_argv:
            argv.extend(self.workiq_argv)
        argv.extend(self.additional_args)
        return argv

    def to_summary_text(self) -> str:
        """確認ページとコピーボタン用のテキスト表現。"""
        lines = [
            "# 起動パラメータ",
            f"- workflow: {self.workflow}",
            f"- dry-run: {self.dry_run}",
            f"- quiet:   {self.quiet}",
            f"- auto-qa: {self.auto_qa}",
            f"- additional_args: {' '.join(self.additional_args) or '(なし)'}",
            f"- workiq:  {' '.join(self.workiq_argv) or '(無効)'}",
            "",
            "# 実行コマンド",
            "python -m hve " + " ".join(self.to_orchestrate_argv()),
        ]
        return "\n".join(lines)


class _WorkflowSelectPage(QWizardPage):
    """Page 1: ワークフロー選択。"""

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setTitle(self.tr("ワークフロー選択"))
        self.setSubTitle("実行するワークフローを選択してください。")

        self._combo = QComboBox()
        for wf_id, desc in _load_workflow_choices():
            self._combo.addItem(format_workflow_label(wf_id, desc), userData=wf_id)

        form = QFormLayout()
        form.addRow("ワークフロー:", self._combo)

        layout = QVBoxLayout(self)
        layout.addLayout(form)

        # QWizard フィールド登録（次ページ以降から参照可能）
        self.registerField("workflow*", self._combo, "currentData")

    def get_workflow(self) -> str:
        return self._combo.currentData() or ""


class _OptionsPage(QWizardPage):
    """Page 2: 共通オプション。"""

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setTitle(self.tr("共通オプション"))
        self.setSubTitle("実行時の共通フラグを設定してください。")

        self._cb_dry_run = QCheckBox(self.tr("--dry-run（実際の変更を行わず計画のみ表示）"))
        self._cb_quiet = QCheckBox(self.tr("--quiet（ログ出力を最小化）"))
        self._cb_auto_qa = QCheckBox(self.tr("--auto-qa（QA フェーズを自動実行）"))
        self._additional = QLineEdit()
        self._additional.setPlaceholderText(self.tr("例: --additional-prompt \"Japan East 前提\""))

        form = QFormLayout()
        form.addRow(self._cb_dry_run)
        form.addRow(self._cb_quiet)
        form.addRow(self._cb_auto_qa)
        form.addRow("追加引数:", self._additional)

        layout = QVBoxLayout(self)
        layout.addLayout(form)

        self.registerField("dry_run", self._cb_dry_run)
        self.registerField("quiet", self._cb_quiet)
        self.registerField("auto_qa", self._cb_auto_qa)
        self.registerField("additional_args", self._additional)

    def get_values(self) -> Dict[str, object]:
        return {
            "dry_run": self._cb_dry_run.isChecked(),
            "quiet": self._cb_quiet.isChecked(),
            "auto_qa": self._cb_auto_qa.isChecked(),
            "additional_args": self._additional.text().strip(),
        }


class _ConfirmPage(QWizardPage):
    """Page 3: 入力内容の確認 + コピーボタン。"""

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setTitle(self.tr("確認"))
        self.setSubTitle("以下の内容で実行します。「完了」を押すと workbench が起動します。")

        self._summary_view = QPlainTextEdit()
        self._summary_view.setReadOnly(True)
        self._summary_view.setLineWrapMode(QPlainTextEdit.LineWrapMode.NoWrap)

        copy_btn = CopyButton(
            get_text=lambda: self._summary_view.toPlainText(),
            tooltip=self.tr("この確認内容をクリップボードにコピー"),
        )

        header = QLabel(self.tr("起動パラメータサマリ"))
        header.setStyleSheet("font-weight: bold;")

        layout = QVBoxLayout(self)
        layout.addWidget(header)
        layout.addWidget(self._summary_view)
        layout.addWidget(copy_btn, alignment=Qt.AlignmentFlag.AlignRight)

    def initializePage(self) -> None:
        wiz = self.wizard()
        if wiz is None:
            return
        result = _collect_result(wiz)
        self._summary_view.setPlainText(result.to_summary_text())


def _collect_result(wiz: QWizard) -> WizardResult:
    additional_raw = wiz.field("additional_args") or ""
    additional_args = additional_raw.split() if isinstance(additional_raw, str) else []
    # Work IQ ページ（存在すれば）から --workiq* 系の argv を抽出
    workiq_argv: List[str] = []
    try:
        from .page_workiq import WorkIQWizardPage

        for pid in wiz.pageIds():
            page = wiz.page(pid)
            if isinstance(page, WorkIQWizardPage):
                workiq_argv = page.to_workiq_argv()
                break
    except Exception:
        # page_workiq の読み込みに失敗しても起動を阻害しない（後方互換）
        workiq_argv = []
    return WizardResult(
        workflow=str(wiz.field("workflow") or ""),
        dry_run=bool(wiz.field("dry_run")),
        quiet=bool(wiz.field("quiet")),
        auto_qa=bool(wiz.field("auto_qa")),
        additional_args=additional_args,
        workiq_argv=workiq_argv,
    )


class LaunchWizard(QWizard):
    """起動ウィザード本体。`exec()` が QDialog.Accepted を返したら `result()` を取得。"""

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setWindowTitle(self.tr("hve — 新規セッション起動ウィザード"))
        self.setWizardStyle(QWizard.WizardStyle.ModernStyle)
        # ページ ID は QWizard 内部で自動採番される
        self.addPage(_WorkflowSelectPage())
        self.addPage(_OptionsPage())
        # Sub-002 / Phase 1: Work IQ 設定ページを追加。
        # 読み込み失敗時（テスト環境等）は無視して従来の 3 ページ構成にフォールバック。
        try:
            from .page_workiq import WorkIQWizardPage

            self.addPage(WorkIQWizardPage())
        except Exception:
            pass
        self.addPage(_ConfirmPage())
        self.resize(720, 520)

    def result_data(self) -> WizardResult:
        """ウィザード完了後に呼び出して結果を取得する。"""
        return _collect_result(self)
