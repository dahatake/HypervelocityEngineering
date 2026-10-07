# conductor toolkit 利用者ガイド

要求定義書・カタログ・System Test の一貫性を保ったまま、アプリケーションを**最高品質・最短時間・最小 Token** で実装するための仕組み（conductor toolkit）の使い方です。
利用者がすることは、エージェントに依頼の Prompt を **1 回**書き、終わったら報告を読んで、回答するか取り込むかを決めることだけです。

> 設計の根拠は計画書「要求定義書・カタログ・System Test の一貫性を保ち、最高品質・最短時間・最小 Token で実装する計画」（文書 ID 202610072130-RD-MaintenanceAnalyticsReport、版 3.1）です。本文中の §番号はこの計画書の節を指します。

## 読む順番

| # | 文書 | こんなときに読む |
|---|---|---|
| 1 | [仕組みの全体像](01-concepts.md) | 何がどう動くのかを最初に理解したい |
| 2 | [導入（インストール・更新・削除）](02-install.md) | 自分のリポジトリに入れたい |
| 3 | [はじめての実行](03-quickstart.md) | VS Code や Copilot CLI で最初の依頼を出したい |
| 4 | [依頼の書き方（/build と run_options）](04-writing-requests.md) | 良い依頼・回答の書き方、承認ポリシーを知りたい |
| 5 | [実行中と終了後](05-during-and-after-run.md) | 進み具合の見方、再開、報告の読み方、取り込み方 |
| 6 | [管理データの書式](06-requirements-format.md) | 要求定義書・カタログ・ID 台帳・System Test の台帳の形 |
| 7 | [設定とカスタマイズ](07-customization.md) | ビルド・テストのコマンド、モデルの割り当て、ゲートの調整 |
| 8 | [スクリプト一覧](08-scripts-reference.md) | `scripts/` の各コマンドの使い方 |
| 9 | [品質ゲートと検査項目](09-quality-gates.md) | hook（G-1〜G-6）と verify（CHK-01〜23）の意味と直し方 |
| 10 | [トラブルシューティング](10-troubleshooting.md) | 止まった・拒否された・失敗したとき |
| 11 | [導入ロードマップと KPI](11-roadmap.md) | 診断から本番運用までの段取りと、効果の測り方 |

## 3 行でわかる使い方

1. 自分のリポジトリのルートで、導入コマンドを 1 回実行します（[02-install.md](02-install.md)）。
   - Windows: `irm https://raw.githubusercontent.com/dahatake/HypervelocityEngineering/main/tools/install.ps1 | iex`
   - macOS / Linux: `curl -fsSL https://raw.githubusercontent.com/dahatake/HypervelocityEngineering/main/tools/install.sh | bash`
2. VS Code の Agents ウィンドウで、Session Target を **Copilot**、Agent を **conductor**、モードを **Autopilot**、Code isolation を **New Worktree** にし、`/build` でやりたいことを書いて送信します（[03-quickstart.md](03-quickstart.md)）。
3. 終わったら `work/runs/<run-id>/run-report.md` を読み、質問票に回答するか、統合ブランチを取り込みます（[05-during-and-after-run.md](05-during-and-after-run.md)）。

## 用語

| 用語 | 意味 |
|---|---|
| conductor（進行役） | 利用者が呼ぶ唯一のエージェント。計画・振り分け・統合・ゲートの判定・報告を行います。 |
| 作業役 | conductor が subagent として呼ぶ custom agent。rd-author、rd-auditor、test-designer、implementer、reviewer の 5 つです。 |
| 管理データ | 要求定義書（`docs/requirements-definition.md`）とカタログ（`docs/catalog.md`）。要求と既存資産の唯一の正本です。 |
| 台帳 | System Test のケースの定義と最新の状態（`tests/system/ledger.json`）。 |
| run | conductor の 1 回の実行。`run-id`（開始日時。例: `202610080900`）で識別します。 |
| `/work` | 一時ファイルの置き場（git の管理対象外。14 日で削除）。作業キュー、進捗、ログ、証跡、報告を置きます。 |
| ゲート | モデルの判断とは無関係に規則を強制する仕組み。hook（G-1〜G-6）と決定的検査 verify（CHK-01〜23）の 2 重です。 |
| 包括承認 | run_options の `approval_policy` で、利用者が事前に「この範囲の AI 提案は推奨どおりでよい」と決めておくこと。 |
