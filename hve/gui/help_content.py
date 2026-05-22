"""hve.gui.help_content — GUI 用ヘルプ説明文の一元辞書。

説明文の根拠（捏造防止）:
  1. `hve/__main__.py` の argparse `help=` 文字列（実行時に build_parser から動的抽出）
  2. `hve/gui/page_workflow_select._WORKFLOW_DESCRIPTIONS`
  3. `users-guide/*.md`

このモジュールは外部から `help_for(key)` を呼ぶことで `HelpEntry` を取得する。
`key` は以下の命名規約:
  - "workflow.<workflow_id>"     : Step 1 ワークフロー
  - "options.<dest_name>"         : Step 2 入力ウィジェット（OrchestrateArgs の dest 名）
  - "workbench.<element>"         : Step 2 表示要素
  - "step_intro.<step_index>"     : 各ステップ上部の説明バナー
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Optional

from PySide6.QtCore import QCoreApplication, QT_TRANSLATE_NOOP


# ----------------------------------------------------------------------
# 翻訳ヘルパー
# ----------------------------------------------------------------------
# 本モジュールはモジュールレベル辞書に日本語説明文を持つため、以下の方針で多言語化する:
#   - 辞書値は ``QT_TRANSLATE_NOOP("help_content", "...")`` でマークする
#     （実行時は引数 2 番目をそのまま返すため挙動は変わらない）。
#   - ``pyside6-lupdate`` がマークを認識し ``.ts`` に抽出する。
#   - 公開ゲッター関数 (`step_intro` 等) で ``_tr()`` を呼び翻訳を適用する。


def _tr(text: str) -> str:
    """``help_content`` コンテキストで翻訳する。空文字はそのまま返す。"""
    if not text:
        return text
    return QCoreApplication.translate("help_content", text)


# ----------------------------------------------------------------------
# データ型
# ----------------------------------------------------------------------


@dataclass(frozen=True)
class HelpEntry:
    short: str
    guide_path: str = ""  # users-guide からのファイル名（例: "01-business-requirement.md"）
    guide_anchor: str = ""


# ----------------------------------------------------------------------
# Step 上部バナー
# ----------------------------------------------------------------------

STEP_INTRO: Dict[int, HelpEntry] = {
    0: HelpEntry(
        short=QT_TRANSLATE_NOOP(
            "help_content",
            "実行したい作業の種類（ワークフロー）を 1 つ選びます。\n"
            "ワークフローごとに『事業要件 → 設計 → 実装』のどの段階を自動化するかが異なります。\n"
            "初めての場合は ARD（要件定義）から始めることを推奨します。",
        ),
        guide_path="hve-gui-getting-started.md",
    ),
    1: HelpEntry(
        short=QT_TRANSLATE_NOOP(
            "help_content",
            "選択したワークフローの実行オプションを設定します。\n"
            "16 カテゴリのアコーディオン形式で、ほとんどの項目は既定値のままで動作します。\n"
            "各項目の右側にある『?』ボタンをクリックすると詳しい説明が表示されます。",
        ),
        guide_path="hve-gui-orchestrator-guide.md",
    ),
    2: HelpEntry(
        short=QT_TRANSLATE_NOOP(
            "help_content",
            "ワークフローの実行状況をリアルタイムに確認します。\n"
            "ステップ状態（○◇●✗⊘）、ログ、作業状況ツリーが表示されます。\n"
            "実行を中断する場合は [停止] ボタンを使用してください。",
        ),
        guide_path="hve-gui-orchestrator-guide.md",
    ),
}


# ----------------------------------------------------------------------
# Step 1: ワークフロー
#
# 根拠: hve/gui/page_workflow_select._WORKFLOW_DESCRIPTIONS と
# users-guide/0X-*.md のファイル名対応。
# ----------------------------------------------------------------------

WORKFLOW_GUIDE_MAP: Dict[str, str] = {
    "ard": "01-business-requirement.md",
    "aas": "02-app-architecture-design.md",
    "aad-web": "03-app-design-microservice-azure.md",
    "asdw-web": "05-app-dev-microservice-azure.md",
    "adfd": "04-app-design-dataflow.md",
    "adfdv": "06-app-dev-dataflow-azure.md",
    "aag": "08-ai-agent.md",
    "aagd": "08-ai-agent.md",
    "akm": "km-guide.md",
    "aqod": "original-docs-review.md",
    "adoc": "sourcecode-documentation.md",
}

_WORKFLOW_SHORT: Dict[str, str] = {
    "ard": QT_TRANSLATE_NOOP("help_content", "事業分析〜要件定義（4 グループ）。Step 1: 企業の事業分析 / Step 2: 要求定義書作成 / Step 3: KPI/OKR 定義 / Step 4: ユースケース作成。既定で Step 2/3/4 が ON（Step 1 は明示的に有効化）。"),
    "aas": QT_TRANSLATE_NOOP("help_content", "アプリケーション設計（Step.1〜Step.7）。アーキテクチャ候補を分析し最適構成を選定します。"),
    "aad-web": QT_TRANSLATE_NOOP("help_content", "Web 画面定義書・サービス定義書・TDD テスト仕様書を生成します。"),
    "asdw-web": QT_TRANSLATE_NOOP("help_content", "Web アプリケーションの開発とデプロイ（TDD RED/GREEN）を実施します。"),
    "adfd": QT_TRANSLATE_NOOP("help_content", "バッチドメイン分析・ジョブ設計を実施します。"),
    "adfdv": QT_TRANSLATE_NOOP("help_content", "データフローアプリの実装と Azure デプロイを実施します。"),
    "aag": QT_TRANSLATE_NOOP("help_content", "AI Agent 構成設計（粒度・詳細）を実施します。"),
    "aagd": QT_TRANSLATE_NOOP("help_content", "AI Agent の実装とデプロイを実施します。"),
    "akm": QT_TRANSLATE_NOOP("help_content", "knowledge/ D01〜D21 を 21 並列で生成・更新します。"),
    "aqod": QT_TRANSLATE_NOOP("help_content", "original-docs/ の質問票生成・横断レビューを実施します。"),
    "adoc": QT_TRANSLATE_NOOP("help_content", "ソースコードからレイヤー別ドキュメントを自動生成します。"),
}


# ----------------------------------------------------------------------
# Autopilot 説明文
# ----------------------------------------------------------------------

_AUTOPILOT_HELP: Dict[str, str] = {
    "autopilot.toggle": QT_TRANSLATE_NOOP(
        "help_content",
        "Application Architecture Catalog の `推薦アーキテクチャ` 列から、APP ごとに "
        "`aad-web → asdw-web` または `adfd → adfdv` を自動判定して実行します。"
        " ON にすると Step 1 の下部に Workflow ごとの入力統合パネルが表示され、"
        " [次へ] 押下時に必須ファイル/設定/認証の事前検証 (precheck) を実行し、"
        " 不足があれば Step 1 に留まります。不足なしで確認 OK すると「Step 2: 実行中」で"
        " 並列実行を開始します（無人実行）。"
        " 実行中はエラー発生 lane のみ停止し、他 lane は継続します。",
    ),
    "autopilot.catalog_path": QT_TRANSLATE_NOOP(
        "help_content",
        "Application Architecture Catalog のパス。空欄のとき "
        "`docs/catalog/app-arch-catalog.md` を使用します。"
        " カスタムパスを指定した場合、そのファイルが存在しないときはエラーになります。",
    ),
    "autopilot.max_parallel": QT_TRANSLATE_NOOP(
        "help_content",
        "Autopilot モードで同時に起動する子 GUI プロセスの最大数。"
        " 範囲 1〜16、既定 4。設定ウィンドウの「Autopilot」セクションで変更できます。",
    ),
}


# ----------------------------------------------------------------------
# Step 2: オプション（dest 名 = OrchestrateArgs フィールド名）
#
# 短い説明は hve/__main__.py の argparse `help=` 文字列を一次ソースとする。
# 動的抽出に失敗した場合のフォールバックとして主要項目のみここに静的に保持する。
# ----------------------------------------------------------------------

_OPTIONS_FALLBACK: Dict[str, str] = {
    "model": QT_TRANSLATE_NOOP("help_content", "使用するモデル名 (デフォルト: Auto)。Auto を指定すると GitHub が最適モデルを自動選択します。"),
    "review_model": QT_TRANSLATE_NOOP("help_content", "敵対的レビューおよび Code Review Agent で使用するモデル（省略時は --model と同じ）。"),
    "qa_model": QT_TRANSLATE_NOOP("help_content", "QA 質問票生成（--auto-qa）で使用するモデル（省略時は --model と同じ）。"),
    "max_parallel": QT_TRANSLATE_NOOP("help_content", "並列実行上限 (デフォルト: 15)。"),
    "auto_qa": QT_TRANSLATE_NOOP("help_content", "QA 自動投入を有効化 (デフォルト: 無効)。"),
    "qa_answer_mode": QT_TRANSLATE_NOOP("help_content", "QA 回答モード。Autopilot=AI が作成した既定回答を全て自動採用 / ユーザー回答=GUIダイアログで回答入力。QA 自動投入が無効のときは無視されます。"),
    "force_interactive": QT_TRANSLATE_NOOP("help_content", "QA 回答入力の TTY 判定をバイパスしてインタラクティブモードを強制する。"),
    "auto_contents_review": QT_TRANSLATE_NOOP("help_content", "Review 自動投入を有効化 (デフォルト: 無効)。"),
    "auto_coding_agent_review": QT_TRANSLATE_NOOP("help_content", "Copilot CLI SDK でローカルにコードレビューを実行する (デフォルト: 無効)。"),
    "auto_coding_agent_review_auto_approval": QT_TRANSLATE_NOOP("help_content", "Code Review Agent の修正プランを全て自動承認 (デフォルト: 無効)。"),
    "workiq": QT_TRANSLATE_NOOP("help_content", "Work IQ 経由の M365 データ参照を有効化する (@microsoft/workiq のインストールが必要)。"),
    "workiq_dxx": QT_TRANSLATE_NOOP("help_content", "AKM Work IQ 取り込み対象 Dxx をカンマ区切りで指定（例: D01,D04）。"),
    "workiq_draft": QT_TRANSLATE_NOOP("help_content", "QA フェーズで質問ごとに Work IQ 回答ドラフトを生成する。"),
    "workiq_prompt_qa": QT_TRANSLATE_NOOP("help_content", "Work IQ の QA 用プロンプトを上書きする。"),
    "workiq_prompt_km": QT_TRANSLATE_NOOP("help_content", "Work IQ の KM 用プロンプトを上書きする。"),
    "workiq_prompt_review": QT_TRANSLATE_NOOP("help_content", "Work IQ の Original Docs レビュー用プロンプトを上書きする。"),
    "workiq_per_question_timeout": QT_TRANSLATE_NOOP("help_content", "Work IQ: QA 質問ごとのクエリタイムアウト秒数。"),
    "workiq_request_timeout": QT_TRANSLATE_NOOP("help_content", "Work IQ MCP サーバーへのツール呼び出し 1 回あたりのタイムアウト秒数（既定 5 分）。Copilot SDK の MCP クライアントが発行する -32001 (Request timed out) を防ぐための設定。"),
    "create_issues": QT_TRANSLATE_NOOP("help_content", "GitHub Issue を作成する。新規ブランチと PR が自動的に作成されます（--repo と GH_TOKEN が必要）。"),
    "create_pr": QT_TRANSLATE_NOOP("help_content", "ローカル実行後に GitHub PR を作成する（--repo と GH_TOKEN が必要）。"),
    "ignore_paths": QT_TRANSLATE_NOOP("help_content", "git add 時に除外するパス (スペース区切りで複数指定可)。"),
    "repo": QT_TRANSLATE_NOOP("help_content", "リポジトリ (owner/repo 形式)。REPO 環境変数からも取得可能。"),
    "issue_title": QT_TRANSLATE_NOOP("help_content", "Issue 作成時の Root Issue タイトルを上書きする。"),
    "verbose": QT_TRANSLATE_NOOP("help_content", "詳細出力 (--verbosity verbose と同等)。"),
    "quiet": QT_TRANSLATE_NOOP("help_content", "出力抑制 (--verbosity quiet と同等)。"),
    "verbosity": QT_TRANSLATE_NOOP("help_content", "コンソール出力レベル: quiet / compact / normal / verbose。"),
    "show_stream": QT_TRANSLATE_NOOP("help_content", "モデル応答のトークンストリーム表示を有効化。"),
    "log_level": QT_TRANSLATE_NOOP("help_content", "Copilot CLI のログレベル: none/error/warning/info/debug/all。"),
    "no_color": QT_TRANSLATE_NOOP("help_content", "ANSI カラー出力を無効化する。"),
    "banner": QT_TRANSLATE_NOOP("help_content", "起動時バナー表示を制御する。"),
    "screen_reader": QT_TRANSLATE_NOOP("help_content", "スクリーンリーダー対応モード: 絵文字を日本語ラベルに置換し、スピナーを無効化。"),
    "timestamp_style": QT_TRANSLATE_NOOP("help_content", "タイムスタンプ表示位置: prefix / suffix / off。"),
    "final_only": QT_TRANSLATE_NOOP("help_content", "DAG 完了時のサマリと各ステップの最終応答のみを出力する。"),
    "cli_path": QT_TRANSLATE_NOOP("help_content", "Copilot CLI 実行ファイルパス (省略時: PATH から自動検出)。"),
    "cli_url": QT_TRANSLATE_NOOP("help_content", "外部 CLI サーバー URL (例: localhost:4321)。"),
    "timeout": QT_TRANSLATE_NOOP("help_content", "idle タイムアウト秒数 (デフォルト: 21600 = 6時間)。"),
    "review_timeout": QT_TRANSLATE_NOOP("help_content", "Code Review Agent レビュー完了待ちタイムアウト秒数 (デフォルト: 7200 = 2時間)。"),
    "branch": QT_TRANSLATE_NOOP("help_content", "ベースブランチ (デフォルト: main)。"),
    "steps": QT_TRANSLATE_NOOP("help_content", "実行ステップをカンマ区切りで指定 (省略時: 全ステップ)。"),
    "app_id": QT_TRANSLATE_NOOP("help_content", "アプリ ID (ASDW/ADFDV 等で使用)。後方互換のため残されています。"),
    "app_ids": QT_TRANSLATE_NOOP("help_content", "対象アプリケーション (APP-ID) — カンマ区切りで複数指定可。"),
    "resource_group": QT_TRANSLATE_NOOP("help_content", "Azure リソースグループ名。"),
    "app_id": QT_TRANSLATE_NOOP("help_content", "データフローアプリ ID (ADFDV 等で使用、カンマ区切り可)。"),
    "usecase_id": QT_TRANSLATE_NOOP("help_content", "ユースケース ID (ASDW 等で使用)。"),
    "sources": QT_TRANSLATE_NOOP("help_content", "AKM: 取り込みソース。qa / original-docs / workiq / both のカンマ区切り組合せ。"),
    "target_files": QT_TRANSLATE_NOOP("help_content", "AKM: 対象ファイルパス (省略時: --sources で選択したソース配下の全件)。"),
    "force_refresh": QT_TRANSLATE_NOOP("help_content", "AKM: 既存 knowledge/ 出力を完全に再生成する。"),
    "custom_source_dir": QT_TRANSLATE_NOOP("help_content", "AKM: custom_source_dir 追加入力（複数指定可）。"),
    "enable_auto_merge": QT_TRANSLATE_NOOP("help_content", "AKM: PR の自動 Approve & Auto-merge を有効にする。"),
    "target_scope": QT_TRANSLATE_NOOP("help_content", "AQOD: チェック対象スコープ（省略時: original-docs/）。"),
    "depth": QT_TRANSLATE_NOOP("help_content", "AQOD: 分析の深さ（standard / lightweight）。"),
    "focus_areas": QT_TRANSLATE_NOOP("help_content", "AQOD: 重点観点（任意）。"),
    "target_dirs": QT_TRANSLATE_NOOP("help_content", "ADOC: ドキュメント生成対象ディレクトリ（カンマ区切り。省略 = 全体）。"),
    "exclude_patterns": QT_TRANSLATE_NOOP("help_content", "ADOC: 除外パターン（カンマ区切り）。"),
    "doc_purpose": QT_TRANSLATE_NOOP("help_content", "ADOC: ドキュメントの主目的（all / onboarding / refactoring / migration）。"),
    "max_file_lines": QT_TRANSLATE_NOOP("help_content", "ADOC: 大規模ファイル分割閾値（行数。デフォルト: 500）。"),
    "company_name": QT_TRANSLATE_NOOP("help_content", "ARD: 対象企業名（Step 1『企業の事業分析』を実行する場合は必須）。"),
    "target_business": QT_TRANSLATE_NOOP("help_content", "ARD: 対象業務名（Step 2 で利用。Step 1 を実行する場合は省略可で、Step 1 の出力から自動生成）。"),
    "survey_base_date": QT_TRANSLATE_NOOP("help_content", "ARD: 調査基準日（省略時は実行日）。"),
    "survey_period_years": QT_TRANSLATE_NOOP("help_content", "ARD: 調査期間年数（省略時は 30）。"),
    "target_region": QT_TRANSLATE_NOOP("help_content", "ARD: 対象地域（省略時は『グローバル全体』）。"),
    "analysis_purpose": QT_TRANSLATE_NOOP("help_content", "ARD: 分析目的（省略時は『中長期成長戦略の立案』）。"),
    "target_recommendation_id": QT_TRANSLATE_NOOP("help_content", "ARD: Step 1（企業の事業分析）完了後に採用する Strategic Recommendation の ID（例: SR-1）。"),
    "attached_docs": QT_TRANSLATE_NOOP("help_content", "ARD: 添付資料パス（カンマ区切り・省略可）。"),
    "additional_prompt": QT_TRANSLATE_NOOP("help_content", "全 Custom Agent の prompt 末尾に追記する文字列 (省略可)。"),
    "context_max_chars": QT_TRANSLATE_NOOP("help_content", "各フェーズで注入するコンテキストの最大文字数（既定 20,000）。"),
    "dry_run": QT_TRANSLATE_NOOP("help_content", "ドライラン（実際の SDK 呼び出しをしない）。"),
    "self_improve": QT_TRANSLATE_NOOP("help_content", "自己改善ループ（Phase 4）を有効化する。"),
    "no_self_improve": QT_TRANSLATE_NOOP("help_content", "自己改善ループ（Phase 4）を無効化する。"),
    "mdq_watch": QT_TRANSLATE_NOOP("help_content", "Markdown ファイルの追加/更新/削除を OS イベントで検知し索引を逐次更新する（既定 ON）。"),
    "mdq_watch_debounce_ms": QT_TRANSLATE_NOOP("help_content", "mdq watcher のデバウンス間隔（ms、既定 500）。"),
}


# 各オプションがどのワークフローに関連するかでガイドリンクを切り替える用
_OPTIONS_GUIDE_HINT: Dict[str, str] = {
    "company_name": "01-business-requirement.md",
    "target_business": "01-business-requirement.md",
    "survey_base_date": "01-business-requirement.md",
    "survey_period_years": "01-business-requirement.md",
    "target_region": "01-business-requirement.md",
    "analysis_purpose": "01-business-requirement.md",
    "target_recommendation_id": "01-business-requirement.md",
    "attached_docs": "01-business-requirement.md",
    "sources": "km-guide.md",
    "target_files": "km-guide.md",
    "force_refresh": "km-guide.md",
    "custom_source_dir": "km-guide.md",
    "enable_auto_merge": "km-guide.md",
    "target_scope": "original-docs-review.md",
    "depth": "original-docs-review.md",
    "focus_areas": "original-docs-review.md",
    "target_dirs": "sourcecode-documentation.md",
    "exclude_patterns": "sourcecode-documentation.md",
    "doc_purpose": "sourcecode-documentation.md",
    "max_file_lines": "sourcecode-documentation.md",
    "workiq": "workflow-reference.md",
    "workiq_akm_review": "workflow-reference.md",
    "workiq_akm_ingest": "workflow-reference.md",
    "workiq_dxx": "workflow-reference.md",
    "workiq_draft": "workflow-reference.md",
    "workiq_draft_output_dir": "workflow-reference.md",
    "workiq_prompt_qa": "workflow-reference.md",
    "workiq_prompt_km": "workflow-reference.md",
    "workiq_prompt_review": "workflow-reference.md",
    "workiq_per_question_timeout": "workflow-reference.md",
    "workiq_request_timeout": "workflow-reference.md",
}

_DEFAULT_OPTIONS_GUIDE = "hve-gui-orchestrator-guide.md"


# ----------------------------------------------------------------------
# Step 2: カテゴリ見出し（C1〜C16）
#
# 根拠: hve/gui/page_options.py の _setup_ui で定義されている各カテゴリ。
# ガイドリンクは users-guide の関連ページへ。
# ----------------------------------------------------------------------

_CATEGORY_HELP: Dict[str, HelpEntry] = {
    "C1": HelpEntry(
        short=QT_TRANSLATE_NOOP("help_content", "使用するモデル名を選択します。Auto を選ぶと GitHub が最適モデルを自動選択します。レビュー用 / QA 用は省略時メインモデルを継承します。コンソール出力レベルもここで設定します。"),
        guide_path="hve-gui-orchestrator-guide.md",
    ),
    "C2": HelpEntry(
        short=QT_TRANSLATE_NOOP("help_content", "同時に起動するサブタスクの並列上限を設定します（既定: 15）。多くすると速くなりますが Copilot のレート制限に当たりやすくなります。"),
        guide_path="hve-gui-orchestrator-guide.md",
    ),
    "C3": HelpEntry(
        short=QT_TRANSLATE_NOOP("help_content", "QA フェーズ・敵対的レビュー・Code Review Agent の自動投入を制御します。すべて既定では無効です。"),
        guide_path="hve-gui-orchestrator-guide.md",
    ),
    "C4": HelpEntry(
        short=QT_TRANSLATE_NOOP("help_content", "Work IQ (Microsoft 365 データ参照) の有効化と詳細設定を行います。@microsoft/workiq のインストールが必要です。"),
        guide_path="workflow-reference.md",
    ),
    "C5": HelpEntry(
        short=QT_TRANSLATE_NOOP("help_content", "GitHub Issue / PR の自動作成を設定します。--repo と GH_TOKEN が必要です。"),
        guide_path="hve-cli-orchestrator-guide.md",
    ),
    "C7": HelpEntry(
        short=QT_TRANSLATE_NOOP("help_content", "MCP Server 設定ファイル・Copilot CLI 実行ファイルパス・外部 CLI サーバー URL を設定します。"),
        guide_path="hve-cli-orchestrator-guide.md",
    ),
    "C8": HelpEntry(
        short=QT_TRANSLATE_NOOP("help_content", "idle タイムアウトとレビュー完了待ちタイムアウトの秒数を設定します（既定: 21600 / 7200 秒）。"),
        guide_path="hve-gui-orchestrator-guide.md",
    ),
    "C9": HelpEntry(
        short=QT_TRANSLATE_NOOP("help_content", "ベースブランチと実行ステップ（カンマ区切り）を設定します。"),
        guide_path="hve-gui-orchestrator-guide.md",
    ),
    "C10": HelpEntry(
        short=QT_TRANSLATE_NOOP("help_content", "APP-ID / リソースグループ / データフローアプリ ID / ユースケース ID 等、ワークフロー固有の対象を指定します。"),
        guide_path="02-app-architecture-design.md",
    ),
    "C11": HelpEntry(
        short=QT_TRANSLATE_NOOP("help_content", "AKM ワークフロー固有: 取り込みソース・対象ファイル・強制再生成・追加入力ディレクトリ等を設定します。"),
        guide_path="km-guide.md",
    ),
    "C12": HelpEntry(
        short=QT_TRANSLATE_NOOP("help_content", "AQOD ワークフロー固有: チェック対象スコープ・分析の深さ・重点観点を設定します。"),
        guide_path="original-docs-review.md",
    ),
    "C13": HelpEntry(
        short=QT_TRANSLATE_NOOP("help_content", "ADOC ワークフロー固有: 対象ディレクトリ・除外パターン・ドキュメントの主目的・大規模ファイル分割閾値を設定します。"),
        guide_path="sourcecode-documentation.md",
    ),
    "C14": HelpEntry(
        short=QT_TRANSLATE_NOOP("help_content", "ARD ワークフロー固有: 対象企業名・対象業務・調査基準日・調査期間・対象地域・分析目的・添付資料を設定します。"),
        guide_path="01-business-requirement.md",
    ),
    "C15": HelpEntry(
        short=QT_TRANSLATE_NOOP("help_content", "全 Custom Agent の prompt 末尾に追記する文字列、コンテキスト最大文字数を設定します。"),
        guide_path="hve-gui-orchestrator-guide.md",
    ),
    "C16": HelpEntry(
        short=QT_TRANSLATE_NOOP("help_content", "ドライラン・Self-Improve（自己改善ループ）等の実行制御を設定します。"),
        guide_path="hve-gui-orchestrator-guide.md",
    ),
}


def category_help(cat_key: str) -> HelpEntry:
    entry = _CATEGORY_HELP.get(cat_key)
    if entry is None:
        return HelpEntry(short="")
    return HelpEntry(short=_tr(entry.short), guide_path=entry.guide_path, guide_anchor=entry.guide_anchor)


# ----------------------------------------------------------------------
# Step 2: Workbench 表示要素
# ----------------------------------------------------------------------

_WORKBENCH_HELP: Dict[str, HelpEntry] = {
    "header1": HelpEntry(
        short=QT_TRANSLATE_NOOP("help_content", "アプリ名・選択ワークフロー・実行番号を表示します。"),
        guide_path="hve-gui-orchestrator-guide.md",
    ),
    "header2": HelpEntry(
        short=QT_TRANSLATE_NOOP("help_content", "各ステップの状態を記号で表示します: ○=未着手 / ◇=実行中 / ●=完了 / ✗=失敗 / ⊘=スキップ。"),
        guide_path="hve-gui-orchestrator-guide.md",
    ),
    "log_pane": HelpEntry(
        short=QT_TRANSLATE_NOOP("help_content", "ワークフロー実行中のログをリアルタイム表示します。右上のコピーボタンで全文をコピー可能。"),
        guide_path="hve-gui-orchestrator-guide.md",
    ),
    "task_tree": HelpEntry(
        short=QT_TRANSLATE_NOOP("help_content", "セッションのサブタスク階層を表示します。Cloud Agent Orchestrator 実行時に各 Sub-issue が枝として現れます。"),
        guide_path="hve-gui-orchestrator-guide.md",
    ),
    "user_actions": HelpEntry(
        short=QT_TRANSLATE_NOOP("help_content", "実行中にユーザー操作が必要な事項（QA 入力待ち等）を表示します。"),
        guide_path="hve-gui-orchestrator-guide.md",
    ),
    "footer": HelpEntry(
        short=QT_TRANSLATE_NOOP("help_content", "コンテキスト消費量・選択モデル・経過時間を表示します。"),
        guide_path="hve-gui-orchestrator-guide.md",
    ),
    "stop_button": HelpEntry(
        short=QT_TRANSLATE_NOOP("help_content", "実行中のオーケストレーターをグレースフルに停止します（SIGTERM 相当）。"),
        guide_path="hve-gui-orchestrator-guide.md",
    ),
}


# ----------------------------------------------------------------------
# argparse からの動的抽出
# ----------------------------------------------------------------------

_argparse_cache: Optional[Dict[str, str]] = None


def _load_argparse_helps() -> Dict[str, str]:
    """`hve/__main__.py` の orchestrate サブパーサから dest -> help を取得する。

    インポートに失敗した場合は空 dict を返す（フォールバック辞書のみ使用）。
    """
    global _argparse_cache
    if _argparse_cache is not None:
        return _argparse_cache

    result: Dict[str, str] = {}
    try:
        import argparse as _ap

        from hve.__main__ import _build_parser  # type: ignore

        parser = _build_parser()
        # orchestrate サブパーサを取得
        for action in parser._actions:  # noqa: SLF001
            if isinstance(action, _ap._SubParsersAction):  # noqa: SLF001
                orch = action.choices.get("orchestrate")
                if orch is None:
                    continue
                for sub_action in orch._actions:  # noqa: SLF001
                    if sub_action.dest and sub_action.help:
                        # 改行を 1 行にまとめる
                        result[sub_action.dest] = " ".join(str(sub_action.help).split())
    except Exception:
        pass

    _argparse_cache = result
    return result


# ----------------------------------------------------------------------
# 公開 API
# ----------------------------------------------------------------------


def step_intro(step_index: int) -> HelpEntry:
    entry = STEP_INTRO.get(step_index)
    if entry is None:
        return HelpEntry(short="")
    return HelpEntry(short=_tr(entry.short), guide_path=entry.guide_path, guide_anchor=entry.guide_anchor)


def workflow_help(workflow_id: str) -> HelpEntry:
    short = _WORKFLOW_SHORT.get(workflow_id, "")
    return HelpEntry(
        short=_tr(short),
        guide_path=WORKFLOW_GUIDE_MAP.get(workflow_id, ""),
    )


def option_help(dest: str) -> HelpEntry:
    """Step 2 オプション用説明文を取得する。

    優先順位:
      1. argparse から動的抽出した help
      2. _OPTIONS_FALLBACK 静的辞書
      3. 空文字（ボタン非表示の合図）
    """
    helps = _load_argparse_helps()
    short = helps.get(dest) or _OPTIONS_FALLBACK.get(dest, "")
    guide = _OPTIONS_GUIDE_HINT.get(dest, _DEFAULT_OPTIONS_GUIDE)
    return HelpEntry(short=_tr(short), guide_path=guide)


def workbench_help(element: str) -> HelpEntry:
    entry = _WORKBENCH_HELP.get(element)
    if entry is None:
        return HelpEntry(short="")
    return HelpEntry(short=_tr(entry.short), guide_path=entry.guide_path, guide_anchor=entry.guide_anchor)


def users_guide_dir() -> Path:
    """`users-guide/` の絶対パスを返す（リポジトリルートから解決）。"""
    here = Path(__file__).resolve()
    # hve/gui/help_content.py から 2 階層上がリポジトリルート
    repo_root = here.parent.parent.parent
    return repo_root / "users-guide"


def guide_url(guide_path: str, anchor: str = "") -> Optional[str]:
    """ローカルの users-guide ファイルへの `file://` URL を返す。

    ファイル不在時は None。
    """
    if not guide_path:
        return None
    path = users_guide_dir() / guide_path
    if not path.exists():
        return None
    url = path.as_uri()
    if anchor:
        url += "#" + anchor
    return url
