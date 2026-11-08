**日本語** | [English](06-quality-gates.en.md)

# 6. 検査と CI

EABK Lite の品質の仕組みは、決定的な検査です。手元の `scripts/verify.py` と CI の `ebak-verify` が同じ検査をします。CI は検査だけで、データ層の修復は手元で `python scripts/rdfix.py --full --apply` を実行して同じ変更に含めます。節目には rd-auditor が意味を監査します。プロンプトや個人のメモリには依りません。規則（AGENTS.md）と検査がリポジトリにあるので、複数の人・複数の PC でも同じように効きます。

| 層 | いつ | 何をするか | 止めるか |
|---|---|---|---|
| `verify.py` | 変更を終える前（AGENTS.md の規則） | データ層の検査と、ビルド・テストのコマンド | exit 1 で知らせる |
| CI `ebak-verify` | push・pull request | `verify.py` と同じ検査 | ワークフローの失敗 |
| 監査（rd-auditor） | 節目に利用者が依頼 | 要求の矛盾・目的とのずれ・曖昧な記述 | 止めない（指摘だけ） |

## 6.1 hook はありません

EABK Lite には hook も、依頼への定型文の自動付与もありません。ツールの実行を拒否したり、作業を差し戻したりする仕組みはなく、役割・編集の範囲・ブランチによるゲートもありません。規則を守れているかどうかは、verify と CI の検査で確かめます。毎回伝えたい前提があれば、自分の Copilot の instructions に書きます。

旧版から更新するときは `--clean`（クリーンインストール）を使うと、旧版の hook のファイルも削除されます（[7.4](07-troubleshooting.md#74-インストール更新)）。

## 6.2 検査プロファイル（lite と full）

`rdcheck.py check`・`verify.py`・`rdfix.py` が報告する CHK の範囲を、プロファイルで選びます。

| プロファイル | 報告する CHK | 使う場面 |
|---|---|---|
| `lite`（既定） | `checks.lite_checks` の CHK（既定は CHK-01・02・03・05・09・12・17・19・24） | ふだんの変更、`verify.py`、CI の ebak-verify |
| `full` | CHK-00〜34 のすべて | 節目の監査（rd-auditor は `--profile full --show-warnings` で実行します）、書式の警告を見たいとき、新しく書いた要求定義書を整えるとき |

- 範囲は `scripts/ebak.config.json` の `checks.profile` で決めます。1 回だけ変えるときは `--profile lite|full` を付けます（設定より優先）。検査のつまみはプロファイルだけです。例: `python scripts/verify.py --docs-only --profile full --show-warnings`。
- lite では、範囲外の CHK は出力にも終了コードにも影響しません。lite は構造と追跡性（ID の重複・再利用、参照先の実在、AC とテストのつながり、System Test の保護）だけを見ます。
- 要約の行は `rdcheck: errors=N warnings=M base=… profile=lite` です。
- プロファイルは `rdcheck.py check`・`verify.py`・`rdfix.py`（`--full` を含む）に同じように効き、例外はありません。そのため `rdfix.py --full` は、同じプロファイルの `verify.py --docs-only` が合格するときに合格します（カタログの同期などの機械的な修復は、どのプロファイルでも同じように行います）。

## 6.3 verify の検査項目

`scripts/verify.py` が実行する検査です。「lite」の列に ● がある CHK が、既定の lite で報告されます。

| ID | lite | 検査内容 | 重大度 | 直し方 |
|---|---|---|---|---|
| CHK-00 | | 要求定義書がない | warn | 要求定義書を作る（skill `requirement-definition`） |
| CHK-01 | ● | ID の重複。ID 台帳にない ID（手で振った ID） | error | `next-id.py` で振り直す。既存のドキュメントは `next-id.py --sync --adopt` |
| CHK-02 | ● | 削除済み・欠番の ID の再利用 | error | `next-id.py` で新しい ID を採番する |
| CHK-03 | ● | AC が実在する要求を参照していない | error | 要求の見出しの下に書くか、`対応する要求:` を付ける |
| CHK-04 | | 要求に上位の G-ID（または既定制約）がない。存在しない G-ID を参照している。承認済みの要求を持たない G-ID がある | error / warn | 上位の欄を直す |
| CHK-05 | ● | MUST 要求に AC も未回答の Q もない | error | AC を追加するか、Q を挙げる |
| CHK-06 | | 承認済みの要求に決定記録（根拠と日付）がない | error | `承認済み（依頼 YYYY-MM-DD）` の形にする |
| CHK-07 | | カタログの要求 ID が要求定義書にない／決定状態・題名が一致しない／承認済み・承認待ち・保留の要求の行がない／同じ要求の行が重複している／機能の表がない | error | `rdfix.py --apply` で要求定義書に合わせる（6.4） |
| CHK-08 | | カタログに書かれたファイルが存在しない | error | パスを直すか「未実装」にする。名前の変更・削除は `rdfix.py --apply` で追従できる |
| CHK-09 | ● | 実装済みの MUST 要求の ID が、テストコードにも manual-tests にもない（未実装なら warn） | error / warn | テスト名かコメントに `FR-012 AC-031` を書く |
| CHK-10 | | system の AC と台帳のケースが双方向に対応していない | warn | 台帳にケースを追加する（`ledger.py`）。対象外になった AC のケースは `ledger.py block` |
| CHK-11 | | `ac_digests` が AC の本文と一致しない | 同上 | ケースを見直し、`ledger.py digests --update` を実行する |
| CHK-12 | ● | 台帳のケースの削除、理由のない command・ac_ids の変更、tests/system の assert の減少 | error | 元に戻す。変更は `ledger.py update --reason` で行う |
| CHK-13 | | 新規・変更した要求・AC に曖昧な語がある | warn | 観察可能な表現に言い換える |
| CHK-14 | | 数値と単位がハードコードされている | warn | PARAM にして `{PARAM-xxx}` で参照する |
| CHK-15 | | 用語集の禁止同義語を使っている | warn | 正しい用語に直す |
| CHK-16 | | 未定義の PARAM の参照、PARAM の表にない PARAM | error | PARAM の表に追加する |
| CHK-17 | ● | 廃止した要求に対して、コード・テスト・カタログが残っている（不整合） | error / warn | 残りを削除し、削除し終えたら本文から外す |
| CHK-18 | | BLOCKED の AC が、未回答の Q・TBD・競合を参照していない／回答済みの Q を参照している | error | ブロックの原因を書く／回答を反映して BLOCKED を外す |
| CHK-19 | ● | コード・テストにある要求 ID・AC ID が要求定義書にない（`checks.id_scan_exclude` のパスは対象外。既定で docs・scripts・SVG の図・`EABK-Studio/**`・Spec Kit の `specs/**/*.md`・`.specify/**` などを除外） | error | ID を直す（廃止した ID の残骸は削除する）。テストデータや資料なら `id_scan_exclude` に足す |
| CHK-20 | | 既定制約の節、ペルソナ表の必須列、要求の構造化欄、承認済み AC の検証レベルがない。決定状態が規定の値でない | error | [03-requirements-format.md](03-requirements-format.md) の形式にする |
| CHK-22 | | 承認済みの決定記録が、依頼・Q・承認依頼・包括承認のどれも根拠として指していない（または、存在しない Q を指している） | error | 根拠を直す |
| CHK-23 | | `/work` が .gitignore にない。docs・tests に一時ファイルが commit されている | error | `rdfix.py --apply` で `/work/` を足す。一時ファイルは /work に移す |
| CHK-24 | ● | 参照先がない: 要求定義書の本文・表やカタログの API・テーブル・共通部品の表に書いた ID が、要求定義書に定義されていない（変更履歴・決定記録・監査指摘の中の、ID 台帳で削除済み・廃止の ID は許す）。カタログが廃止・却下の要求を参照している（warn） | error / warn | ID を直すか、参照先を定義する |
| CHK-25 | | 構造化欄が定義を指していない: 対象エンティティが用語の表にも状態の表にもない。関係する状態がその状態の表にない。本文・AC の `{PARAM-xxx}` が参照パラメータの欄にない（欄にあるのに使っていない PARAM は warn） | error / warn | 用語・状態の表に定義するか、欄を直す |
| CHK-26 | | 孤立した定義: どこからも参照されない PARAM・出典（SRC）、どの要求の対象エンティティでもない状態の表のエンティティ | warn | 参照を足すか、不要なら廃止する |
| CHK-27 | | カタログの表どうしの不整合: 機能の表の「使っている共通部品」が共通部品の表にない。共通部品の表の「使っている要求 ID」が機能の表と一致しない。部品名・API 名・テーブル名の重複。要求の「関連する既存資産」がカタログにない | error | 共通部品の表の要求 ID は `rdfix.py --only catalog --apply` で合わせる。それ以外は表に行を足す |
| CHK-28 | | 外部連携カタログ（`docs/integrations.md`）: 未定義の INT-ID の参照、ID の形式・重複・再利用、必須欄・観点の欄の不足、認証情報らしい値 | error / warn | `next-id.py INT` で採番し、欄を値・なし・TBD（Q-xxx）で埋める。秘密の値は書かない |
| CHK-29 | | 要求の欄がメタデータ定義（`scripts/metadata.json`）にない、または値が許容の形式に合わない | error | 欄名・値を定義に合わせる |
| CHK-30 | | 領域: 要求の領域が割り当て表やカタログの区切りと一致しない、領域の上位 G-ID がない、含む要求の数が違う | error / warn | 領域の欄・割り当て表・カタログの区切りを合わせる |
| CHK-31 | | カタログの同じ種類の表で、列名・列の順序が違う | warn | 先頭の表と同じ列にそろえる |
| CHK-32 | | 1 つの領域の節の直下の項目が上限（PARAM-043）を超えている | warn | 節を分ける |
| CHK-33 | | System Test の重複: 同じ受入基準を、blocked でない台帳のケースが 2 件以上保証している | warn | 残す 1 件に `ledger.py update` で寄せ、残りを `ledger.py block --reason "<残した ID> に統合"` で停止する |
| CHK-34 | | System Test の数: 同じテストファイル・同じ層・同じ要求の、blocked でない台帳のケース（canary・serial を除く）が 2 件以上ある | warn | `python scripts/ledger.py consolidate --apply`。数と遅いコマンドは `ledger.py cost`、上限は `system_test.budget`（`ledger.py cost --check` が超過で exit 1） |

CHK-24〜27 は、要求定義書とカタログを「体系として」保つための検査です。縦のつながり（目的 → 要求 → 受入基準 → 台帳 → 実装・テスト）に加えて、要求と用語・状態・PARAM・出典・カタログの資産の横のつながりも、参照先が実在し双方向で一致していることを確かめます。つながりは `python scripts/rdcheck.py trace <ID または名前>` でたどれます（[5. スクリプト](05-scripts-reference.md)）。

出力は 1 行に 1 指摘（`ERROR CHK-07 docs/catalog.md:12 …`）で、最後に要約の 1 行が出ます。`--show-warnings` を付けると warn も表示します。

## 6.4 データ層の不整合の自動修正（rdfix）

データ層のファイル（要求定義書・カタログ・ID 台帳・System Test の台帳・`.gitignore`）の間の食い違いのうち、要求定義書から機械的に決まるものは、共通の入口 `python scripts/rdfix.py --full --apply` で直せます（確認だけなら `--full`）。

- 呼び出し元は、インストーラ（既定で導入後に 1 回。`--no-repair` で計画だけ、`--skip-verify` で何もしない）と手動の 2 つで、結果は同じです。CI は修復しません（6.5）。
- 終了コードは 0（合格・修復済み）、1（手動の対応が残る・計画がある）、2（実行しなかった・取り消した）です。2 になるのは、排他の待ち時間切れ、書き込みの失敗、要求定義書・外部連携カタログの変化、新しいエラー、想定外のエラーのときで、変更はすべて元に戻します。
- 正本は要求定義書です。rdfix は要求定義書を変更しません。ID 台帳は `next-id.py`、台帳は `ledger.py` を通して直し、台帳の変更は `history` に残します。
- verify が失敗し、自動で直せる不整合があるときは、`HINT rdfix: …` の行が出ます。
- 判断が要る不整合は直さず、`MANUAL <CHK> <位置> <内容>（担当: <作業の種類>）次の行動: …` の行で示します。担当は `要求定義書`、`System Test の台帳`、`コードとカタログ`、`リポジトリ` のどれかで、どのファイルを直す作業かを表します。例: AC の本文が変わった（CHK-11。台帳のケースの見直し）、削除済み・欠番の ID の再利用（CHK-02）、ID 台帳にない ID（CHK-01。手で振った ID かもしれない）。

| 対象（`--only`） | 自動で直すもの | 対応する検査 |
|---|---|---|
| registry | ID 台帳の状態（使用中・廃止・削除済み）、merge=union で重複した行、ID 台帳がないときの作成。`--adopt` を付けたときだけ、台帳にない ID を取り込む | CHK-01 |
| catalog | 機能の表の決定状態・題名を要求定義書に合わせる。要求の行の追加。要求定義書にない要求の行（ファイルの記載がないもの）と重複した行の削除。名前が変わったファイルの参照の付け替えと、存在しないファイルの参照の削除。コードがなくなった廃止の要求の実装ファイルを「なし」にする。共通部品の表の「使っている要求 ID」を機能の表に合わせる | CHK-07・CHK-08・CHK-17・CHK-27 |
| ledger | ケースの欠けた項目、`requirement_ids` を AC の「対応する要求」に合わせる、`ac_digests` の補充と不要な `ac_digests` の削除 | CHK-10・CHK-11 |
| gitignore | `/work/` の追加 | CHK-23 |

`--apply` は、修復を含めたい変更のブランチで実行します。

## 6.5 CI

### ebak-verify

`.github/workflows/ebak-verify.yml` は、pull request と main への push で `scripts/verify.sh --show-warnings` を実行します。検査の範囲は `checks.profile` に従います（既定は lite）。`verify.commands` に登録したビルド・テストも実行します。必要なツールチェーンは、verify のステップの前に追加します（[4.11](04-customization.md#411-ci)）。

### 修復は手元で（CI は修復しない）

CI は検査だけを行い、修復の commit も Issue も作りません。`ebak-verify` が不合格なら、手元で `python scripts/rdfix.py --full --apply` を実行し、修復を同じ変更に含めて push します（要求定義書は変更しません）。読むだけの CI には書き込みの権限が要らず、bot が誰かの PR のブランチへ修復を push すると、ほかの人・PC のブランチと食い違うためです。以前の版の `.github/workflows/ebak-data-layer.yml` は、旧版から `--clean`（クリーンインストール）で更新すると削除されます（[4.11](04-customization.md#411-ci)）。

## 6.6 節目の監査（rd-auditor）

検査で確かめられない意味の問題（要求どうしの矛盾、目的（G-ID）とのずれ、曖昧な記述、カタログ・台帳との意味のずれ）は、節目（リリースの前、大きな変更をまとめる前など）に rd-auditor に監査させます。毎回の変更では使いません。

1. Copilot の Agent で **rd-auditor** を選び、「差分を監査して」「全量を 3 回で監査して」のように頼みます。差分の既定は `base_branch` との差分です。回数（runs）の既定は、差分が 1 回、全量が 3 回です。
2. rd-auditor は `python scripts/verify.py --docs-only --profile full --show-warnings` と `rdcheck.py stats` の結果を使い、意味の判定に集中します。サブエージェントを使えるときは、各回を並行して独立に行い、多数決をとります。
3. 結果は `work/audit/<日時>/` に、各回の出力 `run<n>.md` と集計の `report.md` として書かれます。過半数の回で出た指摘が「確度高」、それ以外が「要確認」です。
4. rd-auditor は git で管理するファイルを変更しません。指摘を反映するかは利用者が判断し、別の変更として行います（そのときも verify を exit 0 にします）。
