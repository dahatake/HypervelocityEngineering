# Changelog

Enterprise App Build Kit の変更履歴です。版は [Semantic Versioning](https://semver.org/lang/ja/) に従い、正本は `scripts/hvelib.py` の `TOOLKIT_VERSION` です。
版の更新は `python tools/bump-version.py <major|minor|patch|X.Y.Z>` で行います。現在の版は `python tools/install.py --version` で確認できます。

## [Unreleased]

## [0.2.0]

- 実行の高速化（品質のゲートは維持）:
  - 実装ループをパイプラインにしました。conductor は作業役を background で起動し、完了した順に統合して、空いた枠にすぐ次の項目を入れます。`parallel_workers` の既定は 5 です。1 項目は要求 ID 1〜5 個で、縦に切った機能の単位にまとめます。
  - 統合を 1 コマンドにする `scripts/integrate.py` を追加しました（`prepare`・`merge`・`abandon`・`pool`）。worktree はプール（`work/worktrees/<run-id>-w<N>`）として再利用し、ignore されたビルドの生成物を残します。`merge` は verify を `--quick` で実行し（5 項目ごとに全コマンド）、System Test は merge 直前からの差分に関係するケースと canary だけに絞ります（まだ統合していない要求のケースは除きます）。失敗したら統合を取り消して todo に戻します。
  - verify に結果のキャッシュを追加しました。作業ツリーが clean で、HEAD・引数・設定・run の状態が同じなら、PASS を再利用します（implementer のゲートの直後の hook G-4 など）。`--no-cache` で無効にできます。
  - hook G-7 を追加しました。run の実行中に、`models` に値のある作業役をそのモデルなしで呼ぶことを拒否し、実際のモデルを `models.jsonl` に記録します（`gates.enforce_models`）。
  - hook の pre-tool は、読み取りだけの組み込みツールに対して、設定の読み込みや git の呼び出しの前に応答します。hook は `python -S` で起動します。
  - reviewer の対象を、共通部品・契約・テーブルの変更、セキュリティ・個人情報・認証、画面の変更に絞りました（MUST だけでは使いません）。小さな依頼のための軽量モードを conductor に追加しました。test-designer と計画、最終監査の 3 回と System Test の実行を並行させます。最終監査は 3 体の並行と集計 1 体で行います（rd-audit の並行モード・集計モード）。
  - skill `implement-fr` から、画面の規則（`ui-design.md`）と、implementer が使わない原本の節（`original-rd.md`）を分け、毎回読む量を約 35% 減らしました。
  - `run-state.py` が項目と工程の時刻を記録し、`kpi.py run` が流れの指標（工程ごとの時間、実効の並列度、項目あたりの作業時間、統合の直列時間、実際に使ったモデル）を出力します。
- データ層のファイル間の不整合を修正する `scripts/rdfix.py` を追加しました。要求定義書を正本として、カタログ（決定状態・題名・行の不足と重複・名前が変わったファイルの参照・廃止の要求の実装ファイル）、ID 台帳（状態・merge=union で重複した行）、System Test の台帳（欠けた項目・`requirement_ids`・`ac_digests` の不足と残骸）、実行履歴の重複行、`.gitignore` の `/work/` を直します。既定は確認だけで、`--apply` で書き込みます。要求定義書は変更せず、判断が要る不整合は担当の役割とともに `MANUAL` として示します。verify は自動で直せる不整合があるときに `HINT rdfix` を表示し、conductor は「始めに」と工程 6 で実行します。hook は作業役・読み取り専用の役割による `--apply` を拒否します。あわせて `ledger.py repair` を追加しました。
- toolkit を使っている別のリポジトリから、インストールと同じ 1 コマンドでアンインストール・クリーンアップできるようにしました（`tools/uninstall.ps1`・`tools/uninstall.sh`）。`--uninstall` は空になったフォルダー・`__pycache__`・旧マーカーのブロックも削除し、マニフェストがなくても toolkit と同じ内容のファイルを判別して削除します。新しい `--purge`（PowerShell は `-Purge`）は、管理データ・`scripts/hve.config.json`・`/work`・`.gitignore` と `.gitattributes` に追記した行・`*.hve-backup-*` も削除します。
- `/build template` が雛形を表示せず、conductor の「始めに」（`run-state.py start`）や実行中の run の再開に進んでしまう問題を直しました。conductor と skill `build` で雛形の表示を最優先にし、hook（`userPromptSubmitted`）がそのターンの読み取り以外のツールを拒否して、ターンの終了を差し戻さないようにしました。

## [0.1.0]

- 版管理を整理し、現在の版を 0.1.0 としました。
