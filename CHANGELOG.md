# Changelog

Enterprise App Build Kit の変更履歴です。版は [Semantic Versioning](https://semver.org/lang/ja/) に従い、正本は `scripts/ebaklib.py` の `TOOLKIT_VERSION` です。
版の更新は `python tools/bump-version.py <major|minor|patch|X.Y.Z>` で行います。現在の版は `python tools/install.py --version` で確認できます。

## [Unreleased]

- conductor にレーンの自動判定を追加しました（`run-state.py lane decide|confirm|show`）。変えた要求が 3 件以下・queue が 2 項目以下で、セキュリティ・競合・共通部品・未確定・事業目的との不一致がないときだけ fast レーンとし、独立監査・reviewer・全量の多数決を省きます（比較レポートの E-4・E-5 の実測に基づく）。要求の書き戻し・System Test の先行設計・verify・hook は省きません。条件を外れる事象が出たら full に戻します。run-report にレーンと省いた工程、依頼の範囲の充足率を書きます。

## [0.3.0]

- 要求定義書とカタログを、ID と名前でつながった 1 つの体系として保つ検査を追加しました（ISO/IEC/IEEE 29148 の「追跡可能」「一貫している」に相当）。
  - CHK-24: 要求定義書の本文・表とカタログの API・テーブル・共通部品の表に書いた ID が、すべて定義されていること（参照先のないリンクの禁止）。
  - CHK-25: 構造化欄が定義を指していること（対象エンティティ → 用語・状態の表、関係する状態 → 状態の表、`{PARAM-xxx}` ⇔ 参照パラメータの欄）。
  - CHK-26（warn）: どこからも参照されない PARAM・SRC・状態の表のエンティティ。
  - CHK-27: カタログの表どうしの双方向の一致（機能の表「使っている共通部品」⇔ 共通部品の表「使っている要求 ID」、名前の重複、「関連する既存資産」の実在）。
  - CHK-07 を強化しました。題名の不一致、承認済み・承認待ち・保留の要求の行の不足、行の重複、機能の表がないことを error にします（これまでは `rdfix.py` が直すだけで、verify は止めませんでした）。
- `rdcheck.py trace <ID|名前>` を追加しました。要求の上流（G・出典）・横（用語・状態・PARAM）・下流（AC・台帳のケース・カタログ・コード）と、G・エンティティ・PARAM・共通部品から要求への逆向きのつながりを表示します（`--json` 可）。
- `rdfix.py` の catalog が、共通部品の表の「使っている要求 ID」を機能の表に合わせます（CHK-27）。
- 既存の要求定義書に導入すると、状態の表に定義していない「関係する状態」などが CHK-25 で error になります。`python scripts/verify.py --docs-only --show-warnings` で確認し、rd-author に「状態の表と用語の表を要求に合わせて整える。意味は変えない」と依頼してください。
- verify の高速化（実測: 統合の再試行が環境起因の timeout で長引いた）。
  - 結果のキャッシュの鍵を HEAD から tree hash に変えました。同じ内容なら commit や worktree が違っても再利用します。
  - 環境起因の失敗（vitest の `Timeout calling` など）は 1 回だけ自動で再実行します（`verify.retry_on` / `verify.retry_flaky`）。
  - verify.commands に `cache_files` を追加しました。依存のファイルが変わっていなければ、`npm ci` などをスキップします。
- 工程 4 の分割並行化（`part: n/N`）、1 項目の AC の上限（12 個）、台帳の書き込みの排他ロック、`models` が空のときの HINT を追加しました。
- 計算資源の活用（0.3.0）。
  - `parallel_workers` の既定を `auto` にしました（2 コア・6 GB につき 1 体、最大 8 体）。各 worker に CPU スレッドを「コア数 × 1.5 ÷ worker 数」で渡します（`HVE_CPUS`、`VITEST_MAX_WORKERS` など）。実測（vitest・20 コア・8 並列）で、全コアを使わせると timeout が 1 件出て、4 スレッドずつにすると出ませんでした。
  - `verify.commands` の `"parallel": true` で、独立した工程を同時に実行します。`ledger.py run --jobs N|auto`（`system_test.jobs`）で System Test を同時に実行します（`"serial": true` のケースは単独）。
  - hook の起動で git を呼ばなくしました（`.git` の走査と HEAD の直接読み）。読み取り系以外のツールで 260 ms → 150 ms です。
  - Azure は既定で使いません。使う条件を [4.9](users-guide/04-customization.md) に書きました。
- 修正: 導入時に、この配布元自身の要求定義書・台帳・Studio のコードの ID が利用者のリポジトリーに混ざる不具合を直しました（雛形は `tools/templates/` から配る。CHK-19 の対象から Studio の同梱ファイルを除外）。
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
- toolkit を使っている別のリポジトリから、インストールと同じ 1 コマンドでアンインストール・クリーンアップできるようにしました（`tools/uninstall.ps1`・`tools/uninstall.sh`）。`--uninstall` は空になったフォルダー・`__pycache__`・旧マーカーのブロックも削除し、マニフェストがなくても toolkit と同じ内容のファイルを判別して削除します。新しい `--purge`（PowerShell は `-Purge`）は、管理データ・`scripts/ebak.config.json`・`/work`・`.gitignore` と `.gitattributes` に追記した行・`*.ebak-backup-*` も削除します。
- `/build template` が雛形を表示せず、conductor の「始めに」（`run-state.py start`）や実行中の run の再開に進んでしまう問題を直しました。conductor と skill `build` で雛形の表示を最優先にし、hook（`userPromptSubmitted`）がそのターンの読み取り以外のツールを拒否して、ターンの終了を差し戻さないようにしました。

## [0.1.0]

- 版管理を整理し、現在の版を 0.1.0 としました。
