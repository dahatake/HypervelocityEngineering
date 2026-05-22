"""hve.gui.page_options_ard — ARD 添付ファイル D&D ペイン。

設計書 §7 対応。

機能:
  - ドラッグ & ドロップで複数ファイルを受け入れる
  - 各ファイルを `doc_convert.py` で Markdown 化
  - 複数ファイルの場合は起点ファイル（business_requirement.md として採用するもの）を選択
  - 結果を `<repo>/docs/attached/` に保存し、`--attached-docs` 用のパス文字列を生成

起点ファイルの扱い（§7.4 暫定設計）:
  - ARD ワークフロー Step 2 が `docs/business-requirement.md` を自動生成・上書きする可能性があるため、
    起点ファイルも `docs/attached/business-requirement-input.md` という別名で保存する。
  - その後 `--target-business "docs/attached/business-requirement-input.md"` を渡すことで
    ARD Step 2 (Targeted) の入力として扱われることを期待する（実コード検証は §13.6 で TBD）。
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING, List, Optional

from PySide6.QtCore import Qt, QThread, Signal
from PySide6.QtGui import QDragEnterEvent, QDropEvent
from PySide6.QtWidgets import (
    QButtonGroup,
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QPushButton,
    QRadioButton,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from .copy_button import CopyButton
from .doc_convert import ConversionResult, convert_file, is_supported

if TYPE_CHECKING:
    from .br_generator import BRGenerationConfig


# ARD 起点ファイルとして配置する別名（§7.4）
ORIGIN_OUTPUT_NAME = "business-requirement-input.md"

# 添付ファイル保存先（リポジトリルートからの相対）
ATTACHED_SUBDIR = "docs/attached"


# --------------------------------------------------------------------------
# 起点ファイル選択ロジック（QApplication 非依存・テスト容易性）
# --------------------------------------------------------------------------


def choose_origin_file(candidates: List[Path]) -> Optional[Path]:
    """テスト容易性のためダイアログから分離した純関数版の "デフォルト" 選択。

    複数候補があれば先頭を返す（GUI 側でユーザー選択を受ける前提）。
    候補が空なら None。
    """
    if not candidates:
        return None
    return candidates[0]


# --------------------------------------------------------------------------
# 起点選択ダイアログ
# --------------------------------------------------------------------------


class _OriginPickerDialog(QDialog):
    """複数ファイル投入時に「business_requirement.md として採用するもの」を選択。"""

    def __init__(
        self,
        candidates: List[Path],
        *,
        parent: Optional[QWidget] = None,
        preselect: Optional[Path] = None,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle(self.tr("起点ファイル選択"))
        self.setModal(True)
        self._candidates = candidates
        self._chosen: Optional[Path] = None

        layout = QVBoxLayout(self)
        layout.addWidget(QLabel(
            self.tr("business_requirement.md として採用するファイルを 1 つ選択してください:")
        ))

        self._group = QButtonGroup(self)
        self._group.setExclusive(True)
        for i, c in enumerate(candidates):
            radio = QRadioButton(c.name)
            radio.setProperty("path_index", i)
            if preselect is not None and c == preselect:
                radio.setChecked(True)
            elif preselect is None and i == 0:
                radio.setChecked(True)
            layout.addWidget(radio)
            self._group.addButton(radio)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self._on_accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def _on_accept(self) -> None:
        checked = self._group.checkedButton()
        if checked is None:
            self.reject()
            return
        idx = checked.property("path_index")
        if isinstance(idx, int) and 0 <= idx < len(self._candidates):
            self._chosen = self._candidates[idx]
        self.accept()

    def chosen(self) -> Optional[Path]:
        return self._chosen


# --------------------------------------------------------------------------
# AttachmentPane: ドラッグ & ドロップを受け付けるメインペイン
# --------------------------------------------------------------------------


class _DropZone(QWidget):
    """D&D を受け付けるエリア。`files_dropped(List[Path])` を emit。"""

    files_dropped = Signal(list)

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setAcceptDrops(True)
        self.setMinimumHeight(80)
        self.setStyleSheet(
            "border: 2px dashed #90caf9; background: #e3f2fd; "
            "color: #1565c0; border-radius: 6px;"
        )
        layout = QVBoxLayout(self)
        label = QLabel(self.tr("📥 ここにファイルをドロップ\n"
                       "（.md / .txt / .csv / .html / .docx / .pdf / .xlsx）"))
        label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(label)

    def dragEnterEvent(self, event: QDragEnterEvent) -> None:  # type: ignore[override]
        if event.mimeData().hasUrls():
            event.acceptProposedAction()
        else:
            event.ignore()

    def dropEvent(self, event: QDropEvent) -> None:  # type: ignore[override]
        urls = event.mimeData().urls()
        paths: List[Path] = []
        for url in urls:
            local = url.toLocalFile()
            if local:
                paths.append(Path(local))
        if paths:
            self.files_dropped.emit(paths)
            event.acceptProposedAction()
        else:
            event.ignore()


class AttachmentPane(QWidget):
    """ARD 添付ファイルペイン。

    使い方:
      pane = AttachmentPane()
      pane.attached_docs_string()  # `--attached-docs` 用文字列
      pane.target_business_path()  # `--target-business` 用パス
    """

    files_changed = Signal()
    # 要求定義書生成完了時に出力相対パスを通知（page_options.py 経由で target_business に自動セット）
    business_requirement_generated = Signal(str)

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self._results: List[ConversionResult] = []
        self._origin_src: Optional[Path] = None  # ユーザーが選んだ起点ファイル (元パス)
        self._repo_root: Path = Path.cwd()
        self._br_worker: Optional["_BRGenWorker"] = None

        self._setup_ui()

    # ----------------------------------------------------------
    # 公開 API
    # ----------------------------------------------------------

    def set_repo_root(self, root: Path) -> None:
        self._repo_root = root

    def attached_docs_string(self) -> str:
        """`--attached-docs` 用のカンマ区切りパス文字列を返す（成功した変換のみ）。"""
        paths = [
            self._rel_to_root(r.converted_path)
            for r in self._results
            if r.ok and r.converted_path is not None
        ]
        return ",".join(paths)

    def target_business_path(self) -> Optional[str]:
        """起点ファイルの相対パス（`--target-business` 用）。"""
        for r in self._results:
            if r.ok and r.src_path == self._origin_src and r.converted_path is not None:
                # 起点は特別な別名で配置されているはず
                return self._rel_to_root(r.converted_path)
        return None

    # ----------------------------------------------------------
    # UI
    # ----------------------------------------------------------

    def _setup_ui(self) -> None:
        header_label = QLabel(self.tr("── 添付資料（ドラッグ&ドロップ可） ──"))
        header_label.setStyleSheet("font-weight: bold; padding: 4px;")

        self._drop_zone = _DropZone()
        self._drop_zone.files_dropped.connect(self._on_files_dropped)

        browse_btn = QPushButton(self.tr("ファイルを選択..."))
        browse_btn.clicked.connect(self._on_browse_clicked)
        # ラベル幅に収まるサイズへ (水平のみ Fixed、垂直は Preferred でフォント/DPI 追従)
        browse_btn.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Preferred)
        browse_row = QHBoxLayout()
        browse_row.setContentsMargins(0, 0, 0, 0)
        browse_row.addWidget(browse_btn)
        browse_row.addStretch()

        list_label = QLabel(self.tr("取り込み済みファイル:"))
        list_label.setStyleSheet("font-weight: bold; padding-top: 8px;")

        self._list = QListWidget()
        self._list.setMinimumHeight(120)

        copy_btn = CopyButton(
            get_text=self._summary_text,
            tooltip=self.tr("取り込みリストをコピー"),
        )

        change_origin_btn = QPushButton(self.tr("起点を変更..."))
        change_origin_btn.clicked.connect(self._on_change_origin)

        clear_btn = QPushButton(self.tr("取消"))
        clear_btn.clicked.connect(self._on_clear)

        actions_row = QHBoxLayout()
        actions_row.addWidget(change_origin_btn)
        actions_row.addWidget(clear_btn)
        actions_row.addStretch()
        actions_row.addWidget(copy_btn)

        self._status_label = QLabel(
            self.tr("★ = business_requirement-input.md の起点として採用")
        )
        self._status_label.setStyleSheet("color: #666; padding: 4px;")

        # 要求定義書生成ボタン（取り込み済みファイルが1件以上ある時のみ有効化）
        # ラベルは短く保ち、生成先パス等の詳細はツールチップで案内する。
        self._generate_br_btn = QPushButton(
            self.tr("要求定義書を生成")
        )
        self._generate_br_btn.setEnabled(False)
        self._generate_br_btn.setToolTip(
            self.tr(
                "取り込み済みファイルから docs/business-requirement.md を生成または更新します。"
                "既存ファイルがある場合は章単位でマージします。"
            )
        )
        self._generate_br_btn.clicked.connect(self._on_generate_br_clicked)
        # ラベル幅に収まるサイズへ (水平のみ Fixed、垂直は Preferred でフォント/DPI 追従)
        self._generate_br_btn.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Preferred)
        generate_row = QHBoxLayout()
        generate_row.setContentsMargins(0, 0, 0, 0)
        generate_row.addWidget(self._generate_br_btn)
        generate_row.addStretch()

        self._br_progress_label = QLabel("")
        self._br_progress_label.setStyleSheet("color: #444; padding: 4px;")
        self._br_progress_label.setVisible(False)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 8, 0, 0)
        layout.addWidget(header_label)
        layout.addWidget(self._drop_zone)
        layout.addLayout(browse_row)
        layout.addWidget(list_label)
        layout.addWidget(self._list)
        layout.addLayout(actions_row)
        layout.addWidget(self._status_label)
        layout.addLayout(generate_row)
        layout.addWidget(self._br_progress_label)

        # 取り込み件数変化に応じて生成ボタンを有効/無効化
        self.files_changed.connect(self._update_generate_br_btn_state)

    # ----------------------------------------------------------
    # シグナル / イベントハンドラ
    # ----------------------------------------------------------

    def _on_browse_clicked(self) -> None:
        paths, _ = QFileDialog.getOpenFileNames(
            self,
            "添付ファイルを選択",
            str(self._repo_root),
            "すべて対応 (*.md *.markdown *.txt *.csv *.html *.htm *.docx *.pdf *.xlsx);;"
            "Markdown (*.md *.markdown);;"
            "テキスト (*.txt *.csv);;"
            "HTML (*.html *.htm);;"
            "Word (*.docx);;PDF (*.pdf);;Excel (*.xlsx);;すべて (*)",
        )
        if not paths:
            return
        self._on_files_dropped([Path(p) for p in paths])

    def _on_files_dropped(self, paths: List[Path]) -> None:
        """D&D された複数ファイルを変換し、リストに追加する。"""
        out_dir = self._repo_root / ATTACHED_SUBDIR
        new_results: List[ConversionResult] = []
        for p in paths:
            if not p.is_file():
                continue
            if not is_supported(p):
                # 未対応形式は失敗として記録
                new_results.append(ConversionResult(
                    src_path=p,
                    ok=False,
                    error=f"未対応の拡張子: {p.suffix}",
                ))
                continue
            r = convert_file(p, out_dir=out_dir)
            new_results.append(r)

        self._results.extend(new_results)
        self._refresh_list()

        # 起点選択
        success_paths = [r.src_path for r in self._results if r.ok]
        if len(success_paths) == 0:
            # 全て失敗
            err_lines = "\n".join(
                f"- {r.display_name}: {r.error}"
                for r in new_results
                if not r.ok
            )
            if err_lines:
                QMessageBox.warning(
                    self,
                    self.tr("変換失敗"),
                    f"取り込みに失敗しました:\n{err_lines}",
                )
            return

        if len(success_paths) == 1:
            self._set_origin_and_rewrite(success_paths[0])
        else:
            # 既に起点が決まっていて新規追加もない場合はそのまま
            if self._origin_src is None or self._origin_src not in success_paths:
                self._prompt_origin_selection(success_paths)
        self.files_changed.emit()

    def _on_change_origin(self) -> None:
        candidates = [r.src_path for r in self._results if r.ok]
        if not candidates:
            QMessageBox.information(self, self.tr("起点変更"), self.tr("対象ファイルがありません。"))
            return
        if len(candidates) == 1:
            self._set_origin_and_rewrite(candidates[0])
            self._refresh_list()
            return
        self._prompt_origin_selection(candidates)

    def _on_clear(self) -> None:
        ret = QMessageBox.question(
            self,
            self.tr("確認"),
            self.tr("取り込んだファイルのリストを全て削除しますか？\n"
            "（既に docs/attached/ に保存されたファイルは削除しません）"),
        )
        if ret != QMessageBox.StandardButton.Yes:
            return
        self._results.clear()
        self._origin_src = None
        self._refresh_list()
        self.files_changed.emit()

    def _prompt_origin_selection(self, candidates: List[Path]) -> None:
        dlg = _OriginPickerDialog(candidates, parent=self, preselect=self._origin_src)
        if dlg.exec() == QDialog.DialogCode.Accepted:
            chosen = dlg.chosen()
            if chosen is not None:
                self._set_origin_and_rewrite(chosen)
                self._refresh_list()

    def _set_origin_and_rewrite(self, origin_src: Path) -> None:
        """起点ファイルを設定し、対応する変換結果のファイル名を `business-requirement-input.md` に変更する。"""
        self._origin_src = origin_src

        # 全ての成功結果に対して、起点なら別名で再保存・それ以外は元のままにする
        out_dir = self._repo_root / ATTACHED_SUBDIR
        for r in self._results:
            if not r.ok or r.converted_path is None:
                continue
            if r.src_path == origin_src:
                # 別名で再変換
                new_result = convert_file(
                    r.src_path, out_dir=out_dir, out_name=ORIGIN_OUTPUT_NAME
                )
                if new_result.ok and new_result.converted_path is not None:
                    # 元のファイル削除はしない（ユーザーが後から起点を変えるかもしれないため）
                    r.converted_path = new_result.converted_path
                    r.ok = True
                    r.error = None
                else:
                    r.ok = False
                    r.error = new_result.error
            else:
                # 起点以外は通常名に戻す（既に通常名で保存されていれば no-op）
                if r.converted_path.name == ORIGIN_OUTPUT_NAME:
                    new_result = convert_file(r.src_path, out_dir=out_dir)
                    if new_result.ok and new_result.converted_path is not None:
                        r.converted_path = new_result.converted_path

    def _refresh_list(self) -> None:
        self._list.clear()
        for r in self._results:
            if r.ok and r.converted_path is not None:
                star = "★" if r.src_path == self._origin_src else "　"
                text = f"{star} {r.display_name}  →  {self._rel_to_root(r.converted_path)}"
                item = QListWidgetItem(text)
            else:
                text = f"✗ {r.display_name}: {r.error}"
                item = QListWidgetItem(text)
                item.setForeground(Qt.GlobalColor.red)
            self._list.addItem(item)

    def _rel_to_root(self, path: Path) -> str:
        """リポジトリルートからの相対パス文字列を POSIX 形式で返す。"""
        try:
            return path.relative_to(self._repo_root).as_posix()
        except ValueError:
            return path.as_posix()

    def _summary_text(self) -> str:
        lines = ["# 添付資料サマリー", ""]
        for r in self._results:
            if r.ok and r.converted_path is not None:
                star = "★ " if r.src_path == self._origin_src else "  "
                lines.append(f"{star}{r.display_name} → {self._rel_to_root(r.converted_path)}")
            else:
                lines.append(f"✗ {r.display_name}: {r.error}")
        attached = self.attached_docs_string()
        if attached:
            lines.append("")
            lines.append("# --attached-docs")
            lines.append(attached)
        target = self.target_business_path()
        if target:
            lines.append("")
            lines.append("# --target-business")
            lines.append(target)
        return "\n".join(lines)

    # ----------------------------------------------------------
    # 要求定義書 生成（章単位 fan-out, Wave 5）
    # ----------------------------------------------------------

    def _successful_attached_paths(self) -> List[Path]:
        """成功した変換結果の出力パス（添付資料の Markdown 化済みファイル）を返す。"""
        return [
            r.converted_path
            for r in self._results
            if r.ok and r.converted_path is not None
        ]

    def _update_generate_br_btn_state(self) -> None:
        """取り込み済みファイル数に応じてボタンを有効/無効化。"""
        has_any = len(self._successful_attached_paths()) >= 1
        # 実行中はボタン無効
        running = self._br_worker is not None and self._br_worker.isRunning()
        self._generate_br_btn.setEnabled(has_any and not running)

    def _on_generate_br_clicked(self) -> None:
        """要求定義書 生成ボタンクリック時の処理。"""
        paths = self._successful_attached_paths()
        if not paths:
            QMessageBox.information(
                self,
                self.tr("要求定義書 生成"),
                self.tr("取り込み済みのファイルがありません。先に添付資料を取り込んでください。"),
            )
            return

        # 既存ファイル確認
        from .br_generator import OUTPUT_REL_PATH
        output_path = self._repo_root / OUTPUT_REL_PATH
        if output_path.exists():
            ret = QMessageBox.question(
                self,
                self.tr("既存ファイルを更新"),
                self.tr(
                    "既存の {path} を章単位でマージ・更新します。\n"
                    "既存記述は保持し、添付資料からの追加情報のみマージされます。\n"
                    "実行してよろしいですか？"
                ).format(path=OUTPUT_REL_PATH),
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            )
            if ret != QMessageBox.StandardButton.Yes:
                # キャンセル時は進捗ラベルをリセット
                self._br_progress_label.setVisible(False)
                self._br_progress_label.setText("")
                return

        # ワーカー起動
        from .br_generator import BRGenerationConfig

        cfg = BRGenerationConfig(
            repo_root=self._repo_root,
            source_paths=paths,
        )

        self._br_worker = _BRGenWorker(cfg, parent=self)
        self._br_worker.progress.connect(self._on_br_progress)
        self._br_worker.finished_with_result.connect(self._on_br_finished)
        self._br_progress_label.setVisible(True)
        from .business_requirement_template import BR_SECTIONS as _BR_SECTIONS
        self._br_progress_label.setText(
            self.tr("要求定義書を生成中... (0/{total} 章完了)").format(total=len(_BR_SECTIONS))
        )
        self._generate_br_btn.setEnabled(False)
        self._br_worker.start()

    def _on_br_progress(self, completed: int, total: int, heading: str) -> None:
        self._br_progress_label.setText(
            self.tr("要求定義書を生成中... ({completed}/{total} 章完了, 直近: {heading})").format(
                completed=completed, total=total, heading=heading
            )
        )

    def _on_br_finished(
        self, ok: bool, output_rel_path: str, error: str, failed_count: int
    ) -> None:
        # ワーカー後片付け
        self._br_worker = None
        self._update_generate_br_btn_state()

        if ok:
            self._br_progress_label.setText(
                self.tr("✓ {path} を生成しました").format(path=output_rel_path)
            )
            # target_business 自動セット用に通知
            self.business_requirement_generated.emit(output_rel_path)
        elif output_rel_path:
            # 一部失敗だが書き出しは成功
            self._br_progress_label.setText(
                self.tr(
                    "△ {path} を生成しました（{failed} 章で失敗。詳細を確認してください）"
                ).format(path=output_rel_path, failed=failed_count)
            )
            self.business_requirement_generated.emit(output_rel_path)
            QMessageBox.warning(
                self,
                self.tr("要求定義書 生成（一部失敗）"),
                error or self.tr("一部の章で生成に失敗しました。"),
            )
        else:
            self._br_progress_label.setText(self.tr("✗ 要求定義書の生成に失敗しました"))
            QMessageBox.critical(
                self,
                self.tr("要求定義書 生成 失敗"),
                error or self.tr("生成に失敗しました。"),
            )


class _BRGenWorker(QThread):
    """`generate_business_requirement` を別スレッドで実行するワーカー。

    GUI スレッドを止めないために asyncio.run を QThread 内で実行する。
    """

    # (completed, total, heading)
    progress = Signal(int, int, str)
    # (ok, output_rel_path, error_message, failed_count)
    finished_with_result = Signal(bool, str, str, int)

    def __init__(self, config: "BRGenerationConfig", parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self._config = config

    def run(self) -> None:  # type: ignore[override]
        import asyncio as _asyncio

        from .br_generator import generate_business_requirement

        def _progress_cb(completed: int, total: int, heading: str) -> None:
            # QThread から Signal を emit するのは Qt 推奨パターン
            self.progress.emit(completed, total, heading)

        try:
            result = _asyncio.run(
                generate_business_requirement(
                    self._config, progress_callback=_progress_cb
                )
            )
        except Exception as exc:  # pragma: no cover - GUI 起動時のみ到達
            self.finished_with_result.emit(False, "", f"内部エラー: {exc}", 0)
            return

        rel_path = ""
        if result.output_path is not None:
            try:
                rel_path = str(
                    result.output_path.relative_to(self._config.repo_root).as_posix()  # type: ignore[attr-defined]
                )
            except (AttributeError, ValueError):
                rel_path = str(result.output_path)

        self.finished_with_result.emit(
            result.ok,
            rel_path,
            result.error or "",
            result.failed_count,
        )

