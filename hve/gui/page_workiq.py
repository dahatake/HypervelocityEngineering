"""hve.gui.page_workiq — Work IQ 設定ページ（独立モジュール）。

Sub-002 (Phase 1) で導入。本モジュールの目的:

1. 既存実装 `hve.gui.page_options._C4WorkIQ`（QWidget, 12 フィールド）を
   公開クラス名 `WorkIQPage` として再エクスポートし、Work IQ UI の
   正規モジュール位置を明示する。
2. ランチウィザード（`hve.gui.wizard.LaunchWizard`）に組み込み可能な
   `WorkIQWizardPage`（`QWizardPage`）ラッパを提供する。
   `--workiq` を有効化した状態で起動したいユーザー向けに、
   ワークフロー選択 → 共通オプションの後段で Work IQ 設定を集中入力できる。

設計指針:
    - `_C4WorkIQ` のフォーム定義は変更しない（後方互換最優先）。
      本モジュールは委譲のみ行い、フィールド定義は `page_options.py` に残置。
    - `WorkIQWizardPage` は `OrchestrateArgs` インスタンスを受け取り、
      ページ完了時に `to_args(args)` を呼び出して同じ dataclass へ書き戻す。
    - CLI 引数化は `OrchestrateArgs.to_argv()`（既存）が `--workiq*` 12 オプション
      を生成するため、本ページは dataclass を埋めるだけで CLI へ到達する。

設計書参照:
    - 設計書 §6.2 C4 Work IQ（page_options 配下）
    - 設計書 §10.1 OrchestrateArgs フィールド一覧
    - work/Issue-orchestration-refactor/research/W7-* （Sub-001 調査結果）

将来拡張:
    - `_C4WorkIQ` を本モジュールへ物理的に移動するリファクタは別サブタスクで実施。
      その際は `page_options.py` 側を `from .page_workiq import WorkIQPage` で
      置換する単一行変更で完了する想定（本モジュールが互換層となる）。
"""

from __future__ import annotations

from typing import Optional

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QLabel,
    QScrollArea,
    QVBoxLayout,
    QWidget,
    QWizardPage,
)

# 既存実装を委譲先として読み込む。
# 循環インポートを避けるため、トップレベルではなく明示的に同一パッケージ内の
# `page_options` を参照する。
from .page_options import _C4WorkIQ as _LegacyWorkIQWidget
from .orchestrate_args import OrchestrateArgs


# ---------------------------------------------------------------------------
# 公開クラス
# ---------------------------------------------------------------------------

#: Work IQ 設定 UI（QWidget）。`_C4WorkIQ` の公開エイリアス。
#: 旧コードからの参照は `_C4WorkIQ` のままで動作するが、新規参照は
#: `WorkIQPage` を使用すること。
WorkIQPage = _LegacyWorkIQWidget


class WorkIQWizardPage(QWizardPage):
    """ランチウィザード用 Work IQ 設定ページ。

    `WorkIQPage` を内包し、`QWizardPage` プロトコルに適合させる。
    ウィザード完了時に `apply_to(args)` を呼び出すと、保持している
    `WorkIQPage` のフォーム入力が `OrchestrateArgs` に書き戻され、
    `args.to_argv()` を介して `python -m hve orchestrate --workiq* ...`
    の CLI 引数として渡る。

    使用例（疑似コード）::

        wiz = LaunchWizard()
        workiq_page = WorkIQWizardPage()
        wiz.addPage(workiq_page)
        if wiz.exec() == QDialog.Accepted:
            args = OrchestrateArgs()
            workiq_page.apply_to(args)
            # → args.workiq, args.workiq_akm_review, ... が埋まる
            argv = args.to_argv()
    """

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setTitle(self.tr("Work IQ 設定"))
        self.setSubTitle(
            self.tr(
                "Microsoft 365 連携（メール・チャット・会議・ファイル）の設定を行います。"
                "未指定項目は環境変数 / 設定既定値を継承します。"
            )
        )

        # ノート: 既定では空欄のまま「次へ」進めるよう IsCommitPage は False。
        # `--workiq` を未チェックのまま完了した場合、CLI 引数には `--workiq` が
        # 含まれず Work IQ 機能は無効のまま起動する（後方互換）。

        self._widget = WorkIQPage(self)

        # 長いフォームに備えてスクロールエリアに格納
        scroll = QScrollArea(self)
        scroll.setWidget(self._widget)
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QScrollArea.Shape.NoFrame)

        notice = QLabel(
            self.tr(
                "ℹ️ 前提: `@microsoft/workiq` プラグインがインストール済みで、"
                "事前に `npx @microsoft/workiq accept-eula` を実行済みであること。"
            )
        )
        notice.setWordWrap(True)
        notice.setStyleSheet("color: #6a737d; padding: 4px;")
        notice.setTextInteractionFlags(Qt.TextInteractionFlag.TextBrowserInteraction)

        layout = QVBoxLayout(self)
        layout.addWidget(notice)
        layout.addWidget(scroll, stretch=1)

    # ------------------------------------------------------------------
    # 公開 API
    # ------------------------------------------------------------------

    def widget(self) -> QWidget:
        """内包する `WorkIQPage` を返す（テスト用）。"""
        return self._widget

    def apply_to(self, args: OrchestrateArgs) -> None:
        """ページ入力を `OrchestrateArgs` へ書き戻す。

        ウィザード `accept()` 後、もしくは `Confirm` ページ初期化時に呼び出す。
        `_C4WorkIQ.to_args()` の薄いラッパであり、12 フィールドすべてを更新する。
        """
        self._widget.to_args(args)

    def to_workiq_argv(self) -> list[str]:
        """現在のフォーム入力から `--workiq*` 系の CLI 引数のみを抽出する。

        `LaunchWizard` のような最小ウィザードに組み込む際、`OrchestrateArgs`
        全体ではなく Work IQ 関連の引数だけを既存 argv にスプライスしたいケースで
        使用する。実装は `OrchestrateArgs.to_argv()` の出力から
        `--workiq` / `--no-workiq` で始まるトークン（およびその直後の値）を
        順に拾い上げる単純なフィルタ。
        """
        scratch = OrchestrateArgs()
        # to_argv() は workflow 必須なので一時値を埋める（出力からは捨てる）
        scratch.workflow = "_workiq_argv_extract_"
        self._widget.to_args(scratch)
        full = scratch.to_argv()
        result: list[str] = []
        i = 0
        while i < len(full):
            tok = full[i]
            if isinstance(tok, str) and (
                tok.startswith("--workiq") or tok.startswith("--no-workiq")
            ):
                result.append(tok)
                # 直後トークンが別のフラグ（`--` 始まり）でなければ値とみなして拾う
                if i + 1 < len(full):
                    nxt = full[i + 1]
                    if isinstance(nxt, str) and not nxt.startswith("--"):
                        result.append(nxt)
                        i += 2
                        continue
            i += 1
        return result


__all__ = ["WorkIQPage", "WorkIQWizardPage"]
