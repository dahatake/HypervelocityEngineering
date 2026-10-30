# Changelog

Enterprise App Build Kit の変更履歴です。版は [Semantic Versioning](https://semver.org/lang/ja/) に従い、正本は `scripts/ebaklib.py` の `TOOLKIT_VERSION` です。
版の更新は `python tools/bump-version.py <major|minor|patch|X.Y.Z>` で行います。現在の版は `python tools/install.py --version` で確認できます。

## [Unreleased]

- `ledger.py run --select changed`: git diff の追加・変更行に現れる要求 ID・AC ID を優先してケースを選び、ケースごとの選択理由を出力する（NFR-PERF-003 AC-450）。共通コードの変更・diff を解析できない・変更行に ID がない場合は従来どおり広げ、「広げた」理由を出す（広げた集合は従来の選択を含む。AC-451）。
- `integrate.py prepare`: 主の作業ツリーにだけある性能基準証跡（`work/**/evidence/perf-baseline-<commit>.json`）を、commit（ファイル名＝内容の `env.commit`、リポジトリに存在）と内容 sha256（隣の `*.sha256`）が一致するときだけ run worktree に配置する。不一致・別 commit・hash 欠落は配置せず理由を出力（NFR-PERF-003 AC-452）。

- `clean-work.py`: 統合ブランチをチェックアウトしている run 専用 worktree（`run-worktree`）も自動削除する。統合ブランチは detach してから削除し、`work/runs/<id>` は主へ退避して候補別結果を主側の run-report に追記する。未コミット変更があれば worktree と統合ブランチを保持。conductor・users-guide を更新。

- 要求・受入基準・System Test のケースを増やしすぎない（読む量・トークン・実行時間の削減）。
  - `rdcheck.py similar "<文>"|ID [--kind FR|AC]`: 新規に作る前に、似た既存の要求・受入基準を類似度の高い順に表示。`similar --pairs` で統合の候補の組を一覧。`rdcheck.py stats` に `similar_pairs`・`ledger_shared_acs` を追加。
  - `ledger.py add`: 同じ受入基準を保証する有効なケースがあれば追加を拒否し、`ledger.py update` での拡張を案内（例外は `--new-case-reason`）。
  - CHK-33（warn）: 同じ受入基準を保証する有効なケースが複数ある。
  - rd-author・requirement-definition（既存の項目の再利用）・test-designer・system-test-increment・rd-audit（重複の観点）・conductor（run-report に数の増減）の手順に反映。

## [0.5.2]

- 複数 chat で conductor を同時に動かしたときの hook の誤拒否を無くす（FR-1074〜1077、NFR-OPS-009・010）。
  - start-claim に start コマンドの識別子（`ident`）を持たせ、追記・消費・meta への持ち主の記録を排他（`start-claims.lock` を OS のファイルロックで保持。待ちは最大 10 秒。異常終了したプロセスのロックは OS が解放する）で行う。`run-state.py start` は自分の識別子と一致する claim だけを消費する（先着順の消費をやめた）。ロックを得られなければ claim・meta を書かずに失敗の理由を表示する。
  - 所有者なし run の救済（R-2）を厳格化: 候補の run が 1 つ・session が特定でき・他 session の未消費 claim がないときだけ束縛する。持ち主が確定した run は束縛し直さない。
  - 主の作業ツリーに置いた run（`require_worktree:false` など）では、持ち主と別の session の chat に run のゲート（G-5 の編集範囲・deploy・external_write など）を掛けない。役割境界（G-1〜G-3、G-6、force push の禁止）は残る（`users-guide/06-quality-gates.md`）。
  - `/build template` の状態を session ごとのファイル（`template-request-<session>.json`）に分離。
  - 修正: 「実行中は main に直接 commit・merge しない」を、`git -C <path>`・`cd <path>` が指す tree のブランチで判定する（run の worktree での commit の誤拒否）。

- 1 run を 3 時間以内に収める（実行ログの分析: 実装 4 項目以上の run は全件 5.5 時間以上）。
  - `max_hours` の既定を 24 → 2.5 に変更（`limits.max_hours_default`）。上限は `limits.max_hours_cap`（既定 3。夜間実行などは設定で引き上げ可）、工程 6 のための残り時間は `limits.reserve_minutes`（既定 30 分）。`ebaklib.effective_max_hours` が `run-state.py time` / `status` / agentStop hook / `build-request.py` で共通に使われる。超過の許容は 1.25 倍 → +15 分。
  - `worktree_share`: `integrate.py prepare` が worktree の `node_modules` を、導入済みの主の作業ツリーへの junction / symlink にする（lock が同じときだけ。`pool --prune`・`clean-work.py` はリンクだけを外す）。
  - hook: 状態を持たないツール（`sql`・`report_intent` など）も即座に許可。作業役の所要時間を `subagents.jsonl` に記録。
  - `credits`: `run-state.py finish` が、`--credits` なしのとき task 呼び出しとモデルの倍率から AI クレジットを推定して記録。
  - conductor: 1 run の項目は最大 3、時間の 60% で未着手は次の run へ、基点で落ちているテストは調べず報告、reviewer・差し戻しの上限、節目の監査を 1 時間ごとに。
  - implement-fr: `npm ci` の並列・再実行の禁止、`--no-cache`・全件回帰の禁止、`BASELINE-FAIL` の返却。
  - `models`: rd-author・test-designer・reviewer を `claude-sonnet-5.5`、implementer-escalation を `gpt-6.1-sol` に設定。

- 実行履歴の分析（直近の run の工程時間・実効の並列度・`[ST]` 修正 commit 69 件）に基づく速さの改善。
  - `ledger.py run`: 同じ pytest ファイルの command を 1 プロセスにまとめて実行（失敗・未該当は単独で再実行。`--no-batch` / `system_test.batch_pytest: false` で止める）。GUI を含む 45 ケースで 320 秒 → 281 秒。
  - `ledger.py preflight`（新規）: pytest の collect-only で、構文・import の誤りと `-k`・node id の誤り（0 件）を実装の前に検出。test-designer の終了前と工程 4 の完了前に実行（統合後の System Test 失敗による手戻りを減らす）。
  - `rdcheck.py`: 走査対象ファイルの先読み（並行）と読み取りの使い回し。
  - 手順書の読み込み量の削減: `requirement-definition`（62KB → 14KB）と `implement-fr`（37KB → 9KB）の「原本」を `original.md` / `original-fr.md` に分離（内容は変更なし）。作業役は、手順書の表の「必ず読む」節だけを行範囲で読む。表と原本のタグの位置は `tests/toolkit/test_skill_index.py` が照合する。
  - 実装前の直列区間: 工程 2（独立監査）を background で起動し、工程 3・4 と並行して進める（工程 5 の前に完了させる）。監査で直す要求の分だけ、test-designer がケースを作り直す。
  - `scripts/ebak.config.json` の `models`: implementer = `claude-sonnet-5.5`、rd-auditor = `gpt-6.1-sol`（hook G-7 が強制）。
  - GUI テスト: `studio_url` を module scope にし、リポジトリを切り替えるテストは個別のサーバー（`studio_url_own`）へ。表示の待ちの競合を修正。

## [0.5.1]

- 全体の実行時間を短縮するため、conductor の指示を並行化の方向に直しました。実測（実効の並列度 0.78〜2.55、`parallel_workers` の 70% 未達が大半）を根拠にしています。
  - 工程 3: 項目を `parallel_workers` 体を埋められる数に細かく切る（独立な項目が足りなければ要求 1〜2 個まで分ける）。まとめるのは同じファイルを同時に編集してしまう要求だけ。
  - 工程 4: test-designer の並行の閾値を AC 40 個超から 15 個超へ（2〜4 組、1 組 15 AC 前後）。工程 5 の項目は、担当の part の完了時点で始めてよい。
  - 速さの原則: 長い作業（目安 30 分超・AC 12 個超・要求 3 個超）や独立した調査が 2 つ以上あるときは、サブタスクに分けて background の作業役へ並行で渡す。
  - TOOLKIT_VERSION を 0.5.1 に上げました。

## [0.5.0]

- **管理データの階層化・メタデータ定義・関係の索引**を追加しました（FR-1057〜FR-1059、NFR-UX-014、toolkit 0.5.0）。
  - 欄名・必須/任意・許容値は `scripts/metadata.json`（インストール対象）が唯一の定義です。`rdcheck.py check` の CHK-29 が、定義にない欄・許容値外の値を `file:行` つきで報告し、Studio の欄の解析も同じ定義を読みます。要求に任意の欄「領域」「更新日」「版」を書けます（要求・受入基準の文面と決定状態は変わりません）。
  - 領域: 要求定義書に領域の一覧表（`| 領域名 | 上位 G-ID | 含む要求数 |`）と、要求ごとの `- 領域: <名>`、カタログの `#### 領域: <名>` の区切りを書けます。決定記録に領域の割り当て表（`| 要求 ID | 領域 |`）が載るまでは領域は任意で、未所属は件数だけ `INFO` で出ます（FR-1060 の承認後は必須。CHK-30 が未所属・表との不一致・カタログとの不一致を報告）。`rdcheck.py list --area <名>` / `--by-area` で領域別に一覧できます（廃止は件数に含めません）。
  - 関係の索引: `rdcheck.py index [ID ...] [--kind 上位|出典|参照|実装|検証|使用] [--json]` が、要求定義書・カタログ・台帳から（保存せず都度）種類つきの関係を生成し、ID を渡すと逆引きになります。
  - 情報デザイン: 同じ種類のカタログの表の列名・順序の不一致（CHK-31）と、領域に分けた節の直下の項目数が PARAM-043（20 件）を超えたとき（CHK-32。割り当て表の承認後のみ）を警告します。
  - TOOLKIT_VERSION を 0.5.0 に上げました。

- **複数の run を 1 つの VS Code から無操作で完走させる**ための修正です。
  - run ID の衝突をなくしました。worktree とブランチの作成を git の原子的な操作に任せ、同じ分に複数の run を始めても、後から来た側は次の空き ID を使います（以前は exit 4 で開始に失敗）。
  - hook を、セッションが所有する run に固定しました。主の作業ツリーから呼ばれても、別セッションの run を選びません（所有者のない run が 1 件のときだけ、そのセッションの run として記録します）。
  - main への取り込みを `run-state.py land` の 1 コマンドにしました。git の共通ディレクトリの全体ロックで run どうしを直列にし、主の作業ツリーが main で未コミットの変更がなくなるまで待ち、`merge --no-ff` → 統合後の `verify --quick` を行い、競合・失敗なら自動で取り消します（終了コード 0 取り込み済み・1 失敗・2 競合・3 主が未整備）。
  - 全件完了なのに main に未取り込みの run があるとき、agentStop の hook が終了を差し戻し、`land` を実行させます（上限は `gates.agent_stop_max_blocks`）。
  - `parallel_workers: auto` を、同時に動いている他の run の数で割ります（CPU・メモリを run どうしで奪い合わない）。

## [0.4.1]

- **データ層の確認・修復の共通の入口**（`scripts/rdfix.py --full [--apply]`）を、GitHub Actions（`ebak-data-layer.yml`）・インストーラ・手動の 3 つの入口で共有しました（FR-1044・FR-1045、NFR-COMPAT-004、NFR-OPS-007）。終了コードは 0（合格・修復済み）/1（手動対応が残る）/2（実行しなかった・取り消した）。同時に 1 つだけ適用します。要求定義書と外部連携カタログは変更しません。
  - インストーラは、導入・更新の後に既定で `rdfix.py --full --apply` を 1 回呼び、修復した項目・残った手動対応・合否を表示します（修復は commit しません）。`--no-repair` で検査と計画だけ、`--skip-verify` で検査も修復もしません。`--dry-run`・`--check`・`--uninstall`・`--purge` では修復しません。インストーラの終了コードはデータ層の結果で変わりません。以前の導入後の `verify.py --docs-only` の別実行は、この入口に置き換わりました。
  - ワークフローの修復手順を `rdfix.py --full --apply` に置き換えました（ループ防止・fork 保護・最小権限・Issue 化は変更なし）。
  - TOOLKIT_VERSION を 0.4.1 に上げました。

- **専用 worktree での run を自動で開始**します。`run-state.py start` が主の作業ツリーで呼ばれると、worktree を作り、その中で run を開始します（`WORKTREE <path>` を出力）。conductor は以後のコマンドをその worktree を cwd にして実行するため、別の VS Code を開く・依頼を再送する必要はありません。複数の run は別々の worktree で並行して動き、hook（`scripts/hooks/gate.py`）は主の作業ツリー側から呼ばれても、触るパスに応じて対応する run の worktree の状態でゲートを判定します。worktree を作れなかったときだけ従来の `WORKTREE-REQUIRED`（exit 4）で案内します。

- **run ごとに専用の git worktree を必須**にしました。`run-state.py start` は主の作業ツリーでは run を始めず（exit 4・`WORKTREE-REQUIRED <path>`）、統合ブランチ `run/<id>` の専用 worktree を作って案内します（1 つの VS Code で複数の run を動かしても、別々の worktree で行われます）。成功（全件完了）した run は、主の作業ツリーで必ず main へ取り込み、worktree と統合ブランチを自動で清掃します。失敗した run は worktree と統合ブランチを保持し、清掃は利用者が行います。`ebak.config.json` の `run.require_worktree: false` または `--allow-primary` で外せます。

- **外部連携の要求チェックリスト**（FR-1038・FR-1039）を追加しました。`.github/skills/requirement-definition/integration-requirements.md` に 16 観点（問い・要求に書く内容・受入基準の例・書かない設計事項）と要求テンプレートを置き、rd-author（カタログの確認・INT 採番・16 観点の走査・包括承認の除外）と rd-audit（観点の欠落・カタログとの食い違い）の手順書に組み込み、インストールで配ります。

- **外部連携カタログ**（任意の `docs/integrations.md`）を追加しました（FR-1035〜FR-1037、toolkit 0.4.0）。外部アプリ・データとの連携を `#### INT-001 <名前>` の 1 連携 1 項目で記録し、16 観点の欄（値・なし・TBD（Q-xxx））と認証情報を書かない規則を持ちます。`python scripts/next-id.py INT` で採番し、`verify.py --docs-only`（CHK-28）が形式・ID・要求との対応を検査し、`rdcheck.py trace INT-xxx` が参照する要求・受入基準を一覧します。インストールは雛形を、まだないときに限り作ります。手順は [users-guide/11-integration-catalog.md](users-guide/11-integration-catalog.md) です。カタログがないリポジトリの検査・Studio・清掃は従来どおりです。
- **次に実装すべき要求の分析と、時間だけで始める /build の依頼生成**を追加しました（FR-1015・FR-1016）。`python scripts/next-impl.py` が、承認済みで未着手・試験未登録・試験未合格の要求を、依存・優先度・実装状態の順位表と除外の理由つきで出し、`python scripts/build-request.py 60分`（`90m`・`24時間`・`1.5h`）が、許容時間を 1 要求あたり 60 分（PARAM-012）で件数に換算した `/build` 用の依頼を生成します（生成のみ。run は開始しません）。

- **既存アプリの導入（brownfield）** を追加しました（`scripts/adopt.py`・skill `adopt-existing`・[users-guide/10](users-guide/10-adopting-existing-apps.md)）。公開されている知見（再文書化とリエンジニアリングの分離、特性化テスト・golden master、Strangler Fig、ホットスポット分析、LLM による要求逆生成の幻覚対策）を、この toolkit の規則（G-1・G-2・G-3、承認は利用者）に照らして検証し、3 層（事実の棚卸し／逆生成の仮説＝出典と証跡の固定・承認待ち／現状の挙動の固定）で採用しました。`scan`・`request`・`anchor`・`check`・`golden` を提供し、conductor・rd-author・test-designer・rd-auditor・implementer の手順に導入モードを追加しました。

- **EABK Studio**（`EABK-Studio/`。データ層をブラウザーで見る、読み取り専用のローカル Web アプリ）を、toolkit の副機能として配布します。インストールすると対象リポジトリに入り、インストールの最後に起動コマンドを表示します。
  - 役割別のガイドを追加しました: Product Manager・Architect・Software Engineer 向け（各 15 分のチュートリアル・おすすめのリンク・判断できること）と、各画面がどのファイルのどの節・列を読み、どう計算するかのデータリファレンス（実画面の画像つき。`capture-screens.py` で再採取できます）。
  - `studio.py` に `--check`（管理データのファイルの有無と解析件数を表示して終了。データ層がなければ exit 1）と `--role pm|architect|swe`（最初に開く画面）を追加しました。データ層のない `--repo` には、起動せずに案内を出します。`start.ps1`（`-Role`・`-Check`・`-NoOpen`）と `start.sh`（残りの引数）は、オプションをそのまま渡せます。
  - EABK と EABK Studio のユーザーガイドを `users-guide/` の 1 か所にまとめました。Studio のガイドは `EABK-Studio/users-guide/` から [users-guide/studio/](users-guide/studio/README.md) へ移り（導入先では `EABK-docs/studio/`）、章の記号を `S1`〜`S8` にしました。索引 [users-guide/README.md](users-guide/README.md) を、第 1 部（EABK 本体）・第 2 部（Studio）・役割別・目的別の構成に作り直しました。更新時、導入先の旧 `EABK-Studio/users-guide/` は（変更していなければ）削除されます。
  - Studio は `__pycache__` を作らないので、対象リポジトリの `git status` を汚しません。
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
