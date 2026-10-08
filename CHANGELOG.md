# Changelog

Enterprise App Build Kit の変更履歴です。版は [Semantic Versioning](https://semver.org/lang/ja/) に従い、正本は `scripts/hvelib.py` の `TOOLKIT_VERSION` です。
版の更新は `python tools/bump-version.py <major|minor|patch|X.Y.Z>` で行います。現在の版は `python tools/install.py --version` で確認できます。

## [Unreleased]

- データ層のファイル間の不整合を修正する `scripts/rdfix.py` を追加しました。要求定義書を正本として、カタログ（決定状態・題名・行の不足と重複・名前が変わったファイルの参照・廃止の要求の実装ファイル）、ID 台帳（状態・merge=union で重複した行）、System Test の台帳（欠けた項目・`requirement_ids`・`ac_digests` の不足と残骸）、実行履歴の重複行、`.gitignore` の `/work/` を直します。既定は確認だけで、`--apply` で書き込みます。要求定義書は変更せず、判断が要る不整合は担当の役割とともに `MANUAL` として示します。verify は自動で直せる不整合があるときに `HINT rdfix` を表示し、conductor は「始めに」と工程 6 で実行します。hook は作業役・読み取り専用の役割による `--apply` を拒否します。あわせて `ledger.py repair` を追加しました。
- toolkit を使っている別のリポジトリから、インストールと同じ 1 コマンドでアンインストール・クリーンアップできるようにしました（`tools/uninstall.ps1`・`tools/uninstall.sh`）。`--uninstall` は空になったフォルダー・`__pycache__`・旧マーカーのブロックも削除し、マニフェストがなくても toolkit と同じ内容のファイルを判別して削除します。新しい `--purge`（PowerShell は `-Purge`）は、管理データ・`scripts/hve.config.json`・`/work`・`.gitignore` と `.gitattributes` に追記した行・`*.hve-backup-*` も削除します。
- `/build template` が雛形を表示せず、conductor の「始めに」（`run-state.py start`）や実行中の run の再開に進んでしまう問題を直しました。conductor と skill `build` で雛形の表示を最優先にし、hook（`userPromptSubmitted`）がそのターンの読み取り以外のツールを拒否して、ターンの終了を差し戻さないようにしました。

## [0.1.0]

- 版管理を整理し、現在の版を 0.1.0 としました。
