**日本語** | [English](05-scripts-reference.en.md)

# 5. スクリプトリファレンス

すべてのスクリプトは、Python 3.9 以上の標準ライブラリだけで動きます。リポジトリのどこから実行しても、git のルートを基準に動作します。オプションの正確な一覧は `python scripts/<名前>.py --help` で表示できます。出力は短く、LLM がそのまま読める形式です（1 行に 1 指摘、最後に 1 行の要約）。

| スクリプト | 役目 | 書き込むもの |
|---|---|---|
| `scripts/ebaklib.py` | 共通ライブラリ（直接は実行しない） | — |
| `scripts/verify.py`（`.ps1`・`.sh`） | 1 コマンドの決定的な検査（完了の判定） | `/work` のログとキャッシュだけ |
| `scripts/rdcheck.py` | 要求定義書のパーサーと検査・検索 | なし（読み取り専用） |
| `scripts/rdfix.py` | データ層の不整合の自動修正 | カタログ・ID 台帳・台帳・`.gitignore`（`--apply` のときだけ。要求定義書は変更しない） |
| `scripts/entities.py` | エンティティ台帳と企業データカタログとの照合 | なし（読み取り専用） |
| `scripts/extpoints.py` | プロジェクト固有の検査の拡張点（rdcheck・rdfix から使う） | — |
| `scripts/next-id.py` | ID の採番 | `docs/id-registry.md` と採番の記録 |
| `scripts/ledger.py` | System Test の台帳の唯一の書き手 | `tests/system/ledger.json` |
| `scripts/summarize.py` | 長いログの要約 | なし |
| `scripts/adopt.py` | 既存アプリの導入 | `docs/baseline/`・`tests/system/golden/`・`work/import/` |
| `tools/install.py` | 導入・更新・削除 | 導入先のリポジトリ |

## ebaklib.py（共通ライブラリ）

ほかのスクリプトが import するライブラリです。要求定義書・カタログ・ID 台帳・System Test の台帳の解析、`scripts/ebak.config.json` の読み込み、git の操作、`/work` の場所の決定をまとめています。toolkit の版 `TOOLKIT_VERSION`（0.6.0）もここにあります。利用者が直接実行することはありません。

## verify.py（決定的な検査。完了の判定）

```bash
python scripts/verify.py                          # 管理データの検査 ＋ verify.commands（ビルド・テストなど）
python scripts/verify.py --docs-only              # 管理データの検査だけ（要求定義書・カタログ・台帳）
python scripts/verify.py --quick                  # "slow": true のコマンドを飛ばす
python scripts/verify.py --profile full           # 検査プロファイルを指定する（lite | full。設定より優先）
python scripts/verify.py --show-warnings          # 警告も表示する
python scripts/verify.py --no-cache               # キャッシュを使わずに必ず実行する
python scripts/verify.py --base main              # 差分の検査の基準（既定は base_branch との merge-base）
./scripts/verify.sh   /  .\scripts\verify.ps1     # 同じもの（Python を探して verify.py に引数を渡すラッパー）
```

exit 0 なら合格です。`AGENTS.md` の規則では、完了の前にこれを exit 0 にします。検査のつまみは検査プロファイル（`--profile`）だけです（0.5.x から撤去したオプションは [9 章](09-versioning.md) を参照）。CI の `ebak-verify` は `scripts/verify.sh --show-warnings` を実行します。ログの全文は `/work/logs` に保存され、画面には要約だけが出ます。プロジェクトのビルド・テストのコマンドは `scripts/ebak.config.json` の `verify.commands` に書きます（[4. カスタマイズ](04-customization.md)）。

**検査プロファイル:** `scripts/ebak.config.json` の `checks.profile` が `lite`（既定）か `full` かで、報告する CHK が変わります。

| プロファイル | 報告する検査 | 使いどころ |
|---|---|---|
| `lite`（既定） | `checks.lite_checks` の CHK だけ（既定は `CHK-01, CHK-02, CHK-03, CHK-05, CHK-09, CHK-12, CHK-17, CHK-19, CHK-24`。構造と追跡性）。ほかの CHK は出力にも終了コードにも影響しません | 毎回の変更と CI |
| `full` | CHK-00〜34 のすべて（曖昧語の CHK-13、数値の直書きの CHK-14、禁止同義語の CHK-15 などの書式の警告を含む） | 節目の監査（rd-auditor は `--profile full --show-warnings` を使う）、利用者が見たいとき |

書式の警告まで見るときは `python scripts/verify.py --docs-only --profile full --show-warnings` です。

**キャッシュ:** 作業ツリーが clean（commit していない変更も、追跡していないファイルもない）のときの PASS は、`/work/.ebak/verify-cache.json` に記録されます。キーは HEAD・引数・`scripts/ebak.config.json` です。同じ commit に同じ verify を実行すると、キャッシュから即座に `PASS (cached …)` を返します。FAIL は記録しません。無効にするには `--no-cache` か、環境変数 `EBAK_VERIFY_NO_CACHE=1` を使います。

## rdcheck.py（要求定義書のパーサー）

```bash
python scripts/rdcheck.py check [--base REF|none] [--profile lite|full] [--errors-only] [--json]
python scripts/rdcheck.py show FR-012 AC-031 Q-007     # 指定した要求・AC・質問の節だけを表示する（全文を読まずに済む）
python scripts/rdcheck.py list --state 承認済み --priority MUST
python scripts/rdcheck.py list --state 承認待ち         # 承認待ちの要求
python scripts/rdcheck.py list --level system          # System Test の対象になる AC
python scripts/rdcheck.py list --area 受付              # 領域で絞る（--by-area で領域ごとにまとめる。廃止は含めない）
python scripts/rdcheck.py index FR-012 [--kind 検証] [--json]   # 種類（上位・出典・参照・実装・検証・使用）つきの関係。保存せず都度生成
python scripts/rdcheck.py hierarchy                    # 種類→区分→領域→項目の階層（都度生成）
python scripts/rdcheck.py stats                        # 監査のメトリクス（JSON）
python scripts/rdcheck.py similar "入力を中断して再開できる"   # 新規に作る前に、似た既存の要求・AC を探す（--kind FR|AC|CASE|CAT、--top N）
python scripts/rdcheck.py similar --pairs [--min 0.35] # 似た項目の組（統合の候補）
python scripts/rdcheck.py digest AC-031                # AC のダイジェスト（PARAM を展開した本文）
python scripts/rdcheck.py trace FR-012 [--json]        # 要求の上流（G・出典）・横（用語・状態・PARAM）・下流（AC・台帳のケース・カタログ・コード）
python scripts/rdcheck.py trace G-002 申請 PARAM-004   # 目的・エンティティ・PARAM から関係する要求を逆にたどる（影響分析）
python scripts/rdcheck.py trace INT-001                # 外部連携を参照する要求と受入基準
```

`check` の出力は 1 行に 1 指摘（`<ERROR|WARN> <CHK-ID> <場所> <内容>`）と、最後の要約行です。

```text
rdcheck: errors=0 warnings=2 base=… profile=lite
```

`--profile` は `scripts/ebak.config.json` の `checks.profile` より優先します。exit 0 = エラーなし、1 = エラーが 1 件以上です。`--base` の既定値は `base_branch`（既定 `main`）との分岐点（merge-base）で、差分の検査に使います。`none` で比較しません。プロファイルは `rdcheck.py check`・`verify.py`・`rdfix.py` に同じように効きます。

## rdfix.py（データ層の不整合の自動修正）

要求定義書を正本として、カタログ・ID 台帳・System Test の台帳・`.gitignore` をそれに合わせます。**要求定義書と外部連携カタログ（`docs/integrations.md`）は変更しません。** 報告する指摘と合否は、`verify.py` と同じ検査プロファイル（`checks.profile`）に従います。そのため `rdfix.py --full` は、同じプロファイルの `verify.py --docs-only` が合格するときに合格します（カタログの同期などの機械的な修復は、どのプロファイルでも同じように行います）。

```bash
python scripts/rdfix.py                           # 修正の計画を表示する（書き込まない）。直せるものがあれば exit 1
python scripts/rdfix.py --apply                   # 修正を書き込み、rdcheck で確かめる
python scripts/rdfix.py --only catalog,ledger     # 対象を絞る: registry, catalog, ledger, gitignore
python scripts/rdfix.py --adopt --apply           # ID 台帳にない ID も取り込む（手で振った ID でないと確かめたとき）
python scripts/rdfix.py --json
```

データ層の検査（`verify.py --docs-only` と同じ rdcheck）と修復をまとめて行うときは `--full` を付けます。

```bash
python scripts/rdfix.py --full                    # 確認だけ（書き込まない・排他を待たない）
python scripts/rdfix.py --full --apply            # 検査→自動修復→再検査（収束するまで最大 3 回 = PARAM-026）
python scripts/rdfix.py --full --apply --json     # 同じ結果を JSON で（手動対応は chk・file・line・owner・action の欄）
python scripts/rdfix.py --full --apply --lock-wait 60   # 排他の待ち秒を変える（既定 30 秒 = PARAM-027）
```

**出力:** `FIX <CHK> <場所> <内容>`（自動で直す）と `MANUAL <CHK> <場所> <内容>（担当: <作業の種類>）次の行動: …`（判断が要る）の行と、最後の `rdfix: fix=N manual=M mode=…` の 1 行です。「担当」は役割名ではなく、直す作業の種類です。

| 担当 | 直すもの |
|---|---|
| `要求定義書` | 要求定義書の本文（AC の本文、ID の再利用・手で振った ID など）。skill `requirement-definition` の手順で直します |
| `System Test の台帳` | 台帳のケース。`ledger.py update`・`block`・`digests --update` で直します |
| `コードとカタログ` | カタログの実装ファイル・テスト・共通部品 |
| `リポジトリ` | `.gitignore`・ブランチなど、リポジトリ全体の設定 |

出力の例:

```text
MANUAL CHK-11 tests/system/ledger.json AC-001 の本文が…（担当: System Test の台帳）次の行動: …
```

**終了コード:**

| 値 | 意味 |
|---|---|
| 0 = 合格・修復済み | 自動で直すものが残っていない |
| 1 = 対応が残る | 手動対応が残る・修復の計画がある（`--apply` なし）・収束しない |
| 2 = 実行しなかった・取り消した | 排他の待ち時間切れ、すべての変更の取り消し、想定外のエラー |

**安全性（`--full --apply`）:** 同じリポジトリで一度に 1 つだけ実行します（`work/.ebak/rdfix.lock`。後から起動したものは `--lock-wait` の秒数まで待ち、終了したプロセスが残したロックは引き継ぎます）。書き込みは一時ファイルの置き換えで行います。要求定義書・外部連携カタログが変わったとき、書き込みに失敗したとき、修復前になかったエラーが現れたとき、想定外のエラーのときは、すべての変更を取り消して修復前の内容に戻し、exit 2 で終わります。

**入口は 2 つ** で、いずれも同じ `rdfix.py --full [--apply]` を呼びます。CI（`ebak-verify`）は検査だけで、修復しません（読むだけの CI には書き込みの権限が要らず、bot が誰かの PR のブランチへ push すると、ほかの人・PC のブランチと食い違うため）。CI で不合格なら、手元で `rdfix.py --full --apply` を実行して同じ変更に含めます。

1. インストーラ `tools/install.py`: 導入・更新の後に既定で `rdfix.py --full --apply` を 1 回実行します。`--no-repair` は `rdfix.py --full`（検査と計画だけで、書き込まない）、`--skip-verify` は検査も修復もしない、`--dry-run`・`--check`・`--uninstall`・`--purge` は修復しません。修復の取り消し・手動対応が残っても toolkit は残り、インストーラの終了コードはデータ層の結果で変わりません。
2. 利用者・Copilot の手動実行。

どの入口でも要求定義書と外部連携カタログは変更せず、手元の実行は修復を commit しません。

`python scripts/ledger.py repair [--apply]` は、台帳の部分だけの修復です（rdfix が内部で使います）。

## entities.py（エンティティ台帳と企業データカタログとの照合）

```bash
python scripts/entities.py list  [--repo DIR] [--json]            # エンティティ台帳（名前・説明・管理テーブル・使い方・列・関係）
python scripts/entities.py check [--repo DIR] [--json] [--strict] # 企業データカタログとの照合（一致／EABK のみ／企業カタログのみ／名称の揺れ候補）
python scripts/entities.py todo  [--repo DIR] [--json]            # 覆われていないエンティティの ToDo（質問票の行の形式）
```

台帳は、用語表・状態表・各要求の「対象エンティティ」から導出します（専用のファイルは作りません）。管理データにない説明・テーブル・使い方は「説明未記載」などと表示し、推測しません。企業データカタログの参照元は `scripts/ebak.config.json` の `enterprise_data_catalog` で任意に指定します（[4. カスタマイズ](04-customization.md)）。未設定でも動き、「企業データカタログ: 未設定（照合していない）」と報告します。参照元は読み取り専用で、本文を保存・転記しません（名前と `出典:行` だけを出力）。`todo` は質問票の行（ID は採番前）を出力するだけで、管理データを書き換えません。質問票へ転記するときは `next-id.py Q` で採番します。exit 0（`check --strict` は差分・照合不能で 1）。

## extpoints.py（プロジェクト固有の検査の拡張点）

toolkit の `scripts/*.py` を編集せずに、プロジェクト独自の検査を rdcheck・rdfix に足すための仕組みです。直接は実行しません。登録の方法は 2 つで、どちらも `tools/install.py` の更新で消えません。

1. `scripts/ebak.config.json` の `"extensions": {"checks": [{"module": "m", "function": "f", "target": "rdcheck"}]}`（`target` は `rdcheck`・`rdfix`・`both`。既定 `both`）
2. `scripts/ext/*.py` に置く（自動で読み込みます。公開関数がそれぞれ検査になります。`CHECKS = [fn, ...]` で絞れます）

検査は `fn(root, cfg)` で、指摘のリスト（空なら合格）を返します。指摘は文字列、`{level, chk, loc, msg}` の dict、4 要素のタプルのどれでもかまいません。level が `ERROR`（既定）なら不合格、`WARN` なら警告です。読み込めないモジュール・ない関数・例外は握りつぶさず、拡張の名前つきの ERROR として報告します。詳しくは [4. カスタマイズ](04-customization.md) にあります。

## next-id.py（ID の採番）

```bash
python scripts/next-id.py FR                    # FR-013
python scripts/next-id.py NFR-SEC               # NFR-SEC-004
python scripts/next-id.py AC --count 3          # AC-041 AC-042 AC-043
python scripts/next-id.py FR --note "下書き保存"  # ID 台帳にメモを残す
python scripts/next-id.py Q | PARAM | G | SRC | E2E | IT
python scripts/next-id.py INT                   # INT-001（外部連携カタログ docs/integrations.md の ID。[11 章](11-integration-catalog.md)）
python scripts/next-id.py --peek FR             # 採番せずに次の ID を表示する
python scripts/next-id.py --sync                # ID 台帳の状態を本文に合わせる（使用中・廃止・削除済み）
python scripts/next-id.py --sync --adopt        # 台帳にない既存の ID を取り込む（インストール直後）
python scripts/next-id.py --sync --finalize     # 使わなかった採番済みの ID を欠番にする
```

ID はこのスクリプトでだけ採番します（`AGENTS.md` の規則）。次の番号は、max(要求定義書, ID 台帳, `base_branch` 上の同じファイル, System Test の台帳, 作業ツリーで共有する採番の記録) + 1 で決まります。採番した ID は `docs/id-registry.md` と `<git-common-dir>/ebak-id-alloc.json` に記録されるので、同じ PC の別の作業ツリーと同じ ID を出すことはありません。別の PC で同時に採番して重複したときは CHK-01 が検出します（[2. ふだんの進め方](02-daily-workflow.md)）。

## ledger.py（System Test の台帳）

`tests/system/ledger.json` の唯一の書き手です。ケースは削除せず、止めるときは `block` します。`command`・`ac_ids` の変更には `--reason` が必須で、履歴に残ります。pass / fail は、実行したコマンドの終了コードからだけ記録します。`--by` で履歴に残す実行者（自分の名前、`ci` など）を指定できます。

```bash
python scripts/ledger.py summary [-v]
python scripts/ledger.py add --req FR-012 --ac AC-031 --title "…" --layer e2e --command "…" [--canary] [--serial]
                                                    # 同じ AC の有効なケースがあれば拒否（update で広げる。例外は --new-case-reason "理由"）
python scripts/ledger.py update E2E-001 --command "…" --reason "…"     # --title・--ac・--req・--canary も変更できる。理由は必須
python scripts/ledger.py block E2E-001 --reason "…"                   # 削除の代わりに使う
python scripts/ledger.py set E2E-001 pass|fail|blocked|not_run [--evidence PATH] [--reason "…"]
python scripts/ledger.py digests [--update]                           # AC のダイジェスト（PARAM を展開した本文）
python scripts/ledger.py repair [--apply]                             # 要求定義書に合わせて台帳を直す（rdfix.py から使う）
python scripts/ledger.py preflight [--cases ID,..] [--all]            # pytest を collect-only で確認（構文・import の誤り、0 件の選択）
python scripts/ledger.py cost [--top N] [--check]                     # ケース数・テストファイル数・統合できる数・遅いコマンド・予算（--check は超過で exit 1）
python scripts/ledger.py consolidate [--apply] [--reason "…"]         # 同じテストファイル・層・要求のケースを 1 つに統合（既定は計画だけ）
python scripts/ledger.py run --select changed|failed|all [--base REF] [--canary-first] [--stop-on-canary-fail] [--max-minutes N] [--jobs N|auto]
python scripts/ledger.py run --cases E2E-001,IT-002 [--no-record]     # 指定したケースだけ。--no-record は台帳を書き換えない
```

`--select changed` は、git diff の追加・変更行に現れる要求 ID・AC ID に対応するケースを優先して選び、ケースごとに `select <ケース ID>: <理由>` を出力します。共通コードの変更などで絞れないときは広げ、理由に「広げた」と出します。`run` の出力は `<id> <requirement_ids> <pass|fail> <秒> <証跡>` の行と `結果: …` の行です。結果の詳細は `work/system-test/results.json` に保存されます（`--results PATH` で場所を指定できます。`--no-record` のときは台帳を書き換えず、結果は `--results` のファイルにだけ書きます）。同じ commit・きれいな作業ツリーですでに pass または fail したケースは再実行を省きます（強制は `--rerun-passed`・`--rerun-failed`）。

## summarize.py（ログの要約）

```bash
python scripts/summarize.py work/logs/verify-…-unit.log [--max-lines 15] [--tail 5]
npm test 2>&1 | python scripts/summarize.py -
```

テストランナーの集計行、最初の数件の（重複しない）エラー行、末尾の数行だけを出力します。

## adopt.py（既存アプリの導入）

```bash
python scripts/adopt.py scan [--since-days 365] [--json]          # 棚卸し → docs/baseline/inventory.{json,md}
python scripts/adopt.py request [--clusters 6] [--cluster NAME] [--implement] [--stdout]
                                                                  # Copilot のチャットに貼る依頼文 → work/import/adopt-<日時>.md
python scripts/adopt.py anchor SRC-003 src/a.py:10-48 [--note "…"] # 出典の証跡を固定 → docs/baseline/evidence.json
python scripts/adopt.py check [--strict] [--json]                 # 証跡のずれ・回収率・逆生成の要求の検査（exit 1 = 誤り）
python scripts/adopt.py golden add NAME -- CMD ARG...             # 特性化テスト（golden master）
python scripts/adopt.py golden record|check|list [NAME] [--update]
```

`request` は、`<request>`・`<references>` と `<constraints>` の節を持つ依頼文を出力します。既定の `<constraints>` は「承認: 厳格（逆生成の要求は承認待ちのまま）」「実装: しない（コードを変更しない）」で、`--implement` を付けると「実装: 承認済みの要求すべて」になります。出力をそのまま既定のエージェントのチャットに貼ります。`adopt.py` は要求定義書を編集せず、ID も振りません。詳細は [10. 既存のアプリを導入する](10-adopting-existing-apps.md) にあります。

## tools/install.py（導入・更新・削除）

ふつうは `tools/install.ps1`・`tools/install.sh`（このリポジトリを取得して実行する 1 コマンド）から使います。手元の clone からは次のとおりです。

```bash
python tools/install.py --target <導入先> [--dry-run] [--force] [--no-ci]
python tools/install.py --target <導入先> --check        # 更新が必要かを確かめる（必要なら exit 1）
python tools/install.py --target <導入先> --no-repair    # 導入後は rdfix.py --full（検査と計画だけ。書き込まない）
python tools/install.py --target <導入先> --skip-verify  # 導入後の検査も修復もしない
python tools/install.py --target <導入先> --clean        # クリーンインストール（toolkit が入れたものをすべて消してから入れ直す）
python tools/install.py --target <導入先> --uninstall    # 変更していない toolkit のファイルとブロックを削除（管理データと設定は残す）
python tools/install.py --target <導入先> --purge        # --uninstall ＋ 管理データ・設定・/work・追記も削除
python tools/install.py --version
```

| オプション | 動作 |
|---|---|
| `--target DIR` | 導入先のリポジトリ（既定: カレントディレクトリ） |
| `--source DIR` | toolkit のソース（既定: このスクリプトのリポジトリ） |
| `--dry-run` | 書き込まずに、行う操作だけを表示する |
| `--check` | 更新が必要かを確かめる（必要なら exit 1） |
| `--clean` | クリーンインストール。マニフェストに記録されたファイルとこの版の配布物（変更したものも）・`.ebak-backup-*`・設定・ブロック・追記した行・マニフェストを削除してから導入する。管理データ・`/work`・アプリのコードとテストは残す。git リポジトリで未 commit の変更がないときだけ実行する。`--uninstall`・`--purge`・`--check` とは併用できない。PowerShell のラッパーでは `-Clean` |
| `--force` | ローカルで変更した toolkit のファイルも上書き・削除する（`.ebak-backup-*` を残す） |
| `--no-ci` | `.github/workflows/ebak-verify.yml` を入れない |
| `--no-repair` | 導入後の自動修復をせず、`rdfix.py --full` で検査と修復の計画だけを表示する。PowerShell のラッパーでは `-NoRepair` |
| `--skip-verify` | 導入後のデータ層の検査も修復も行わない |
| `--uninstall` / `--purge` | 削除（上の例を参照） |
| `--allow-non-git` | git リポジトリでない場所にも導入する |
| `--version` | toolkit の版を表示して終了する |

行うこと（何度実行しても同じ結果）: 配布物（rd-auditor、skills、`ebak-verify.yml`、`scripts/*`、EABK-Studio。Studio のテスト `EABK-Studio/tests/` は入れません）を入れ、変更していなければ更新します。管理データのひな形（要求定義書・カタログ・外部連携カタログ・ID 台帳・台帳）は、ないときだけ作ります。`scripts/ebak.config.json` は新しいキーを足し、利用者の値を残します（新しい導入の `verify.commands` は空の `[]`）。`.gitignore` に `/work/`（見出し `# Enterprise App Build Kit: temporary files (logs, evidence, notes)`）、`.gitattributes` に `docs/id-registry.md merge=union`、`AGENTS.md` と `.github/copilot-instructions.md` に規則のブロックを足し、`.github/ebak-toolkit.json` に版とハッシュを記録します。最後に `rdfix.py --full --apply` を 1 回実行します（要求定義書は変更せず、修復は commit しません）。

更新は、この版が配布するファイルだけを扱います。旧版が入れて今の版が配布しないファイルは削除せず、マニフェストにも残し（`--clean` で見つけられるように）、件数を「注意」で表示します。旧版からの移行の処理（版ごとの削除リストや設定の書き換え）は持ちません。旧版（0.5.x など）から更新するときは `--clean` を使います。`--clean` の後も、旧版のデータ層のファイル（0.5.x の `docs/run-history.md` など）と、0.5.x の run が残した worktree・`work/*` ブランチは残るので、不要なら手で削除します（[9.4](09-versioning.md#94-旧版から更新するクリーンインストール)）。

## EABK-Studio（データ層のビューアー）

インストールすると、導入先の `EABK-Studio/` に入ります。データ層（要求定義書・カタログ・台帳）を図・表・検索で見る、ローカルの読み取り専用の Web アプリです（日本語・英語）。EABK を入れていない git リポジトリも、HVE の clone から `python EABK-Studio/studio.py --repo <任意の git リポジトリ>` で見られます（コードのモード。FR-1086）。

```text
python EABK-Studio/studio.py [--repo DIR] [--port 8765] [--no-open] [--role pm|architect|swe] [--check]
```

| オプション | 動作 |
|---|---|
| `--repo DIR` | 対象リポジトリ。EABK がなくてもよい（親へさかのぼってデータ層を探し、なければ git のルート）。省略時はカレントディレクトリ（データ層があるか、コードのモードで見られる git リポジトリのとき）、それ以外は Studio 自身のリポジトリ |
| `--port N` | 待ち受けポート（既定 8765。使用中なら次の番号を最大 20 まで試す） |
| `--no-open` | ブラウザーを自動で開かない |
| `--role pm\|architect\|swe` | 最初に開く画面（ダッシュボード／2D マップ／表） |
| `--check` | 管理データのファイルの有無と、解析できた件数・警告を表示して終了。データ層があるか、コードのモードで見られれば exit 0（`mode: code (...) requirement-docs=… requirements=… linked-to-code=… code-files=… test-files=… components=…` の行が出ます）、どちらでもなければ exit 1 |

- ラッパー: `EABK-Studio/start.ps1 [-Repo DIR] [-Port N] [-Role …] [-Check] [-NoOpen]`、`EABK-Studio/start.sh [DIR] [PORT] [studio.py のオプション…]`。
- コードのモードでは、Markdown の表の先頭の列と見出しにある要求 ID（`FR-…`・`NFR-…`。`docs/PRD.md` などを先に読む）、その ID を書いたコードとテスト、コンポーネントにまとめたソースを読み取りだけで導出します。台帳と受入基準は空です。対象は git リポジトリのルートだけで、空のフォルダーや git でないフォルダーは exit 1 です。
- データ層があるときはソースコードを読まず、127.0.0.1 だけで待ち受けます。書き込むのは「整合性保守」で確認して実行した `docs/catalog.md` の題名・決定状態だけです。
- 役割別のガイドは [studio/README.md](studio/README.md) にあります。
