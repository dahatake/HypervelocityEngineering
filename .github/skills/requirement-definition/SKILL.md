---
name: requirement-definition
description: rd-author が、conductor から渡された依頼・回答・資料を、docs/requirements-definition.md と docs/catalog.md の構造化欄つきの要求・受入基準・質問票・決定記録・出典台帳に反映する手順書（要求定義書とカタログの唯一の書き手。コードは変更しない）。ID は next-id.py で採番し、終了前に `verify.py --docs-only` を exit 0 にする。
---
# requirement-definition（rd-author の手順書）

この手順書は、利用者の原本「RequirementDefinition作成」の本文（同じフォルダーの別ファイルにある「原本」）に、conductor による無人の連続実行につなぐための読み替えと規則を加えたものです。

## 読み替え表（原本の指示 → この実行での扱い）

原本は、利用者が 1 本ずつ手で投入する前提で書かれています。conductor が無人で連続実行するため、次のとおり読み替えます。**読み替えと原本が食い違うときは、読み替えを優先します。**

| 原本の指示 | 読み替え | 理由 |
|---|---|---|
| RequirementDefinition「commit と push は行わない。利用者が差分をレビュー」 | rd-author は統合ブランチに `[RD] <要約>` で commit します。利用者のレビューは、最終報告（run-report）と取り込みの判断で行います。 | 無人で連続実行するため |
| RD-FR「依頼をもって承認」「要求定義書を作成または更新」 | implementer は要求定義書を変更しません。要求の誤りや不足は、結果の `CONFLICTS:` に書き、conductor が rd-author に回します。 | 要求の書き手を 1 つにする（GAP-1、H1） |
| SystemTest「対象 AC はシステム全体を通して確かめるもの」 | 「検証レベル: system」の AC にします。 | 判断のぶれをなくす（GAP-5） |
| 3 Prompt「最終報告はチャットで」 | `work/runs/<run-id>/run-report.md` に書きます（conductor）。作業役は 10 行以内の結果を返します。残すべき情報は `/docs` と台帳に転記します。依頼に関係しない既存の問題は、要求定義書の「監査指摘」に書きます。 | 監査結果を消さない（GAP-7） |
| 3 Prompt・SystemTest「ログ、証跡（スクリーンショット）、実行結果の保存先」 | `work/runs/<run-id>/logs/`、`evidence/`、`results.json` にします。台帳には最新の状態（status、last_commit、last_run_at、evidence、history）だけを書きます。 | /docs と tests を永続のものだけにする |
| 3 Prompt「新しい ID は最大番号の続き」 | `python scripts/next-id.py <種別>` で採番します（FR、NFR-<区分>、AC、Q、PARAM、E2E、IT）。 | 並行作業での ID の衝突を防ぐ（GAP-6） |
| RD-FR・SystemTest「承認済みの要求だけを実装・テスト」 | approval_policy で包括承認したものを含みます。決定記録に「包括承認」と書きます。 | 承認待ちで止まらない（§承認ポリシー） |
| 3 Prompt「質問せずに最後まで進める」「<request> <answers> <references> <execution_options> <run_options>」 | 利用者が毎回書く部分は、conductor が作業役への依頼の本文で渡します。原本の入力欄（`<request>` など）は、その置き場所を示すだけです。 | 利用者の Prompt を 1 回にする |

## この役割で追加する規則

### 構造化欄（ルール B。scripts/verify.py が検査します）

```markdown
#### FR-012 入力の中断と再開
- 要求: 申請を入力している利用者は、入力を中断して後で再開したときに、入力済みの内容と未完了の項目を確認できる。
- 決定状態: 承認済み（包括承認 2026-10-08・approval_policy）　出自: AI提案　優先度: SHOULD（中断のたびの再入力が離脱の原因）
- 上位: G-002　出典: SRC-003 §2.1
- 対象エンティティ: 申請　関係する状態: 下書き→提出済み　参照パラメータ: PARAM-004
- 関連する既存資産: 共通部品「下書き保存」
- 受入基準 AC-031: 入力途中で画面を閉じた利用者が、同じアカウントで再び開いたとき、入力済みの値が失われず、未完了の項目が識別できる。保持期間は {PARAM-004} とする。
  - 検証レベル: system
- 受入基準 AC-032: …保持期間を過ぎた下書きは表示されない。
  - 検証レベル: integration
  - BLOCKED: Q-007（保持期間の起点が TBD）
```

- 1 行に複数の欄を書くときは全角スペース（`　`）で区切ります。値がない欄は「なし」と書きます（欄を省きません）。
- 決定状態は「承認済み（依頼 YYYY-MM-DD）」「承認済み（Q-### YYYY-MM-DD）」「承認済み（承認依頼 YYYY-MM-DD）」「承認済み（包括承認 YYYY-MM-DD・approval_policy）」「AI提案／承認待ち」「保留」「却下」「廃止（依頼 YYYY-MM-DD）」のどれかです。
- 受入基準の `検証レベル` は `system`（System Test の台帳と 1:1 で対応）、`integration`、`unit`、`manual`（`docs/manual-tests.md` で確かめる）のどれかです。
- 閾値・期間・件数は「前提・制約」の PARAM の表（`| ID | 名前 | 値 | 単位 | 根拠 | 決定状態 |`）で定義し、本文では `{PARAM-xxx}` で参照します。値が TBD のときは値の欄に `TBD（Q-xxx）` と書きます。
- 用語の表（`| 用語 | 定義 | 禁止同義語 |`）に禁止同義語を書くと、verify が使用を検出します。
- 質問票は表（`| ID | 重要度 | 質問 | 選択肢 | 推奨 | 状態 | 回答 |`）にし、回答を反映したら状態を「回答済み」にします。
- BLOCKED の受入基準は、未回答の Q-ID、TBD、競合のどれかを `BLOCKED:` の欄に書きます。

### つながりの規則（体系としての一貫性。scripts/verify.py が検査します）

要求定義書とカタログは、ID と名前でつながった 1 つのデータです。1 か所を書き換えたら、つながる先も同じ commit で直します。

- 本文・表に書く ID（G・FR・NFR・AC・Q・PARAM・SRC）は、必ず定義済みのものにします。参照先のない ID は書きません（CHK-24）。出典は出典台帳の `SRC-xxx` で書きます。
- 対象エンティティは用語の表か状態の表（`| 対象エンティティ | 状態 | 遷移の条件 |`）に、関係する状態はそのエンティティの状態の表に定義してから使います（CHK-25）。新しいエンティティ・状態は、要求より先に表へ足します。
- 本文・受入基準で `{PARAM-xxx}` を使ったら、その要求の「参照パラメータ」の欄にも書きます（CHK-25）。
- どこからも使われなくなった PARAM・SRC・状態の表のエンティティは、廃止するか参照を足します（CHK-26 の警告）。
- 要求を追加・改題・状態変更したら、カタログの機能の表の行（要求 ID・題名・決定状態）を同じ commit で合わせます。`python scripts/rdfix.py --only catalog --apply` で機械的に合わせられます（CHK-07）。
- 「関連する既存資産」に `共通部品「…」`・`API「…」`・`テーブル「…」` と書くときは、カタログに実在する名前にします（CHK-27）。
- 要求を変更・廃止する前に `python scripts/rdcheck.py trace <ID>` で、つながる AC・台帳のケース・カタログ・コードを確かめ、影響を変更履歴と結果に書きます。エンティティ・PARAM を変えるときは `trace <名前|PARAM-xxx>` で、それを使う要求を洗い出します。

### 既存の項目の再利用（新規に作る前に。数を最適に保つ）

要求・受入基準が増えるほど、各役割が読む量（トークン）、System Test のケースと実行時間、監査の照合の組が増えます。依頼の内容が既存の項目と重なるときは、新規に作らず既存の項目を変更します。新しい目的・対象の要求は、ためらわず追加します。

1. 採番の前に `python scripts/rdcheck.py similar "<書こうとする要求・受入基準の文>"` を実行します（要求だけなら `--kind FR`、受入基準だけなら `--kind AC`）。類似度の高い順に既存の項目が出ます。
2. 出た項目を `rdcheck.py show <ID>` で読み、**目的（上位の G）と対象エンティティが同じ**なら、その項目を変更します。
   - 振る舞いの追加・条件の拡張 → 既存の要求の本文を広げ、受入基準を足すか、既存の受入基準の条件・値を変えます。
   - 閾値・期間の違い → PARAM の値を変えます（新しい要求にしません）。
   - 同じ振る舞いの言い換え → 何も足しません（結果に「既存の ID で充足」と書きます）。
3. 目的か対象が違うときだけ、新規に採番します。
4. `rdcheck.py similar --pairs` で出た似た組（既定の下限 0.35）のうち、依頼の範囲に入るものは、1 つに統合します。台帳のケースの組（`--kind CASE`）は test-designer が残す方に AC を寄せ、もう一方を停止します。残す方を変更し、もう一方を「廃止（依頼 YYYY-MM-DD）」にして、変更履歴に「統合: 廃止した ID → 残した ID」と書きます。依頼の範囲外の組は、監査指摘（カテゴリ: 重複）に書くだけにします。
5. 承認済みの要求の文面を変えるのは、依頼がその変更を含むときだけです（ほかは競合として記録する従来の規則のまま）。

### 外部連携を含む依頼（FR-1039。`integration-checklist.md`・`integration-requirements.md`）

依頼が外部のアプリ・データとの連携（API・ファイル・DB・イベント）を含むときは、要求を書く前に次を行います。

1. 外部連携カタログ（`docs/integrations.md`。ない導入先は雛形から作成）を確認し、既存の連携があれば再利用・更新します。新しい連携は `python scripts/next-id.py INT` で INT-ID を採番し、`#### INT-xxx <名前>` の項目と索引表の行を足します。
2. [integration-requirements.md](integration-requirements.md) の 16 観点（連携先・方向・方式・頻度と量・データ分類と個人情報・認証認可・可用性／SLA・レート制限・エラー／再試行／冪等性・契約／バージョン・変更通知・監視・データ保持・障害時の代替・責任分界・法務／ライセンス）を 1 つずつ走査します。決まらない観点は、質問票（Q-ID）に載せて値を `TBD（Q-xxx）` にし、関係する受入基準を BLOCKED にします。
3. 個人情報・認証認可・外部公開に触れる観点は、approval_policy の包括承認の対象にしません（承認待ちのまま質問票に載せます）。
4. 要求の「関連する既存資産」と構造化欄に、カタログの INT-ID を書きます。要求は同じ文書のテンプレート（基本形と構造化欄・検証レベル付きの受入基準）で書きます。
5. 終了前に `python scripts/verify.py --docs-only` を exit 0 にし、結果に 16 観点の走査（観点番号ごとの扱い）を書きます。

### 承認ポリシー（approval_policy）

| 値 | 動作 |
|---|---|
| `厳格` | 原本のとおり。AI提案は「AI提案／承認待ち」とし、実装しません。 |
| `安全範囲は推奨どおり`（既定） | AI提案と質問票の推奨案のうち、次の条件をすべて満たすものは「承認済み（包括承認 YYYY-MM-DD・approval_policy）」にします。条件: 利用者データ・権限・セキュリティ・プライバシー・課金・法令・外部公開・マスターと ID の体系・取り消せない操作に触れない／PARAM の変更で戻せる／既存の承認済み要求と競合しない。それ以外は承認待ちのままにし、関係する AC を `BLOCKED: Q-xxx` にします。 |
| `すべて推奨どおり` | 上記の除外分野だけを承認待ち・BLOCKED にし、残りはすべて推奨案で「承認済み（包括承認 …）」にします。 |

包括承認した要求は、結果の `APPROVED-BY-POLICY:` に返します（conductor が最終報告に影響の大きい順で載せ、利用者は次の Prompt の `<answers>` で却下・修正できます）。

### 使うスクリプト

| 目的 | コマンド |
|---|---|
| ID の採番（手で振らない） | `python scripts/next-id.py FR`、`python scripts/next-id.py NFR-SEC`、`python scripts/next-id.py AC --count 3`、`Q`、`PARAM` |
| 必要な節だけ読む | `python scripts/rdcheck.py show FR-012 AC-031` |
| 新規に作る前に似た既存の項目を探す | `python scripts/rdcheck.py similar "<文>"`、`similar FR-012`、`similar --pairs`（統合の候補） |
| つながり・影響範囲をたどる | `python scripts/rdcheck.py trace FR-012`、`trace 申請`、`trace PARAM-004` |
| 一覧・件数 | `python scripts/rdcheck.py list --state 承認済み`、`python scripts/rdcheck.py stats` |
| 終了前の検査（G-4） | `python scripts/verify.py --docs-only --show-warnings`（exit 0 にする） |
| 工程 6 の ID 台帳の整理 | `python scripts/next-id.py --sync --finalize`（conductor が実行） |

既存の文書に初めて導入するときは、`python scripts/next-id.py --sync --adopt` で既存の ID を ID 台帳に取り込みます。

### 工程 6 の転記（conductor から依頼されたとき）

`/work` は 14 日で消えるので、残すべき情報を要求定義書に転記します。

| 情報 | 転記先 |
|---|---|
| 包括承認した項目、回答を反映した決定 | 決定記録（「包括承認 YYYY-MM-DD・<run-id>」） |
| 未回答の質問票、承認依頼 | 仮定・未解決事項 |
| 監査の指摘のうち、残っているもの | 監査指摘（`| ID | 日付 | カテゴリ | 重大度 | 位置 | 要約 | 状態 |`） |

---

## 原本 RequirementDefinition作成 の読み方（起動のたびに全文を読まない）

原本の全文は同じフォルダーの `original.md` にあります（内容は変更していません。読み替え表と、この手順書の規則が優先です）。起動のたびに全文を読むと、読み込む量が増えて起動が遅くなります。次の表の「必ず読む」節だけを、`view` の行範囲で読みます。「必要なとき」の節は、その場合だけ読みます。表の行範囲は `tests/toolkit/test_skill_index.py` が原本のタグの位置と照合します（ずれたらテストが落ちます）。

| 節 | 位置 | 読むとき |
|---|---|---|
| `<workflow>` | 32〜41 行 | 必ず読む |
| `<investigation>` | 43〜66 行 | 必ず読む |
| `<audit>` | 68〜96 行 | 必ず読む |
| `<questionnaire>` | 98〜124 行 | 必ず読む |
| `<requirements_document>` | 126〜172 行 | 必ず読む |
| `<evidence_rules>` | 174〜180 行 | 必ず読む |
| `<catalog>` | 230〜243 行 | 必ず読む |
| `<boundaries>` | 245〜253 行 | 必ず読む |
| `<communication>` | 264〜284 行 | 必ず読む |
| `<turn_endings>` | 255〜262 行 | 必ず読む |
| `<ui_policy>` | 200〜228 行 | 画面を持つ要求・UI の依頼を扱うとき |
| `<focus_areas>` | 182〜198 行 | 監査の観点を広げたいとき |
| `<example>` | 161〜168 行 | 要求の書き方の例を見たいとき |
| `<context>` | 24〜30 行 | 管理データの位置づけを確かめたいとき |
