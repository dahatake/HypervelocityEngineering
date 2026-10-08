# Enterprise App Build Kit 詳細ガイド

Enterprise App Build Kit の詳細なリファレンスです。概要・インストール・Quickstart・用語は、リポジトリ直下の [README.md](../README.md) を先に読んでください。


## ドキュメント一覧

| # | ドキュメント | 読むタイミング |
|---|---|---|
| 1 | [依頼の書き方（/build と run_options）](01-writing-requests.md) | よい依頼・回答の書き方や、承認ポリシーを知りたい |
| 2 | [実行中と終了後](02-during-and-after-run.md) | 進捗の確認、再開、報告の読み方、マージの方法を知りたい |
| 3 | [管理データの書式](03-requirements-format.md) | 要求定義書・カタログ・ID 台帳・System Test の台帳のフォーマットを知りたい |
| 4 | [設定とカスタマイズ](04-customization.md) | ビルド・テストのコマンド、モデルの割り当て、ゲートを調整したい。MCP Server・plugin（Work IQ・Azure など）を使いたい |
| 5 | [スクリプトリファレンス](05-scripts-reference.md) | `scripts/` の各コマンドの使い方を知りたい |
| 6 | [品質ゲートと検査項目](06-quality-gates.md) | hook（G-1〜G-6）と verify（CHK-01〜23）の意味と直し方を知りたい |
| 7 | [トラブルシューティング](07-troubleshooting.md) | 止まった・拒否された・失敗した |
| 8 | [導入ロードマップと KPI](08-roadmap.md) | 診断から本番運用までの段取りと、効果の測り方を知りたい |
| 9 | [バージョンアップの手順](09-versioning.md) | 版を上げる（配布元）、導入済みのリポジトリを更新する（利用者） |
## README の各節へのリンク

| 知りたいこと | README の節 |
|---|---|
| 解決する問題と全体のアーキテクチャ | [概要](../README.md#概要) |
| エージェントの責務と書き込み権限 | [エージェントと権限](../README.md#エージェントと権限) |
| run の工程（工程 0〜6） | [1 回の run の流れ](../README.md#1-回の-run-の流れ) |
| インストール・更新・アンインストール | [インストール](../README.md#インストール) |
| 最初の run の出し方と確認項目 | [Quickstart](../README.md#quickstart) |
| 用語 | [用語](../README.md#用語) |
