# 10. 既存のアプリを導入する（Adopt）

ソースコード・設計書・テストがすでにあるアプリで、この toolkit を使うための手順と、その方式を選んだ根拠です。新規開発（要求から作る）と違い、**要求の正本がまだない**ので、データ層（要求定義書・カタログ・System Test の台帳）を先に整えます。

## 10.1 結論（最短の使い方）

```text
python tools/install.py --target <既存のリポジトリ>     # toolkit を入れる（既存のファイルは壊さない）
python scripts/adopt.py scan                              # ① 棚卸し（事実だけ。LLM なし）→ docs/baseline/inventory.md
python scripts/adopt.py request                           # ② /build の依頼文を作る → work/import/adopt-<日時>.md
```

③ 依頼文を、Agent を conductor にして `/build` の後に貼り付けます（要求の仮説づくりと、現状の挙動の固定。コードは変えません）。
④ 報告の「承認待ち（逆生成）」の要求に、`<answers>` で `FR-0xx: 承認` などと回答します。
⑤ 以後は通常の `/build`（変更・追加）です。変えた挙動は `golden check` が検出します。次のまとまりを回収するときは、②から繰り返します。

| コマンド | 役割 | 書く場所 |
|---|---|---|
| `adopt.py scan [--since-days N]` | ファイル・役割・言語・ルート・テーブル・テスト・設計書・churn を集め、機能のまとまりを hotspot 順に並べる | `docs/baseline/inventory.{json,md}` |
| `adopt.py request [--clusters N] [--cluster 名前] [--implement]` | 未回収のまとまりを選び、`/build` の依頼文にする（既定は `scope: なし`・`approval_policy: 厳格`） | `work/import/` |
| `adopt.py anchor SRC-xxx ファイル:開始-終了` | 要求の出典（SRC）に、コードの範囲のハッシュを固定する（空白だけの変更は無視） | `docs/baseline/evidence.json` |
| `adopt.py check [--strict] [--json]` | 証跡のずれ（DRIFT）・回収率・出典のない逆生成の要求・包括承認の誤り・golden の状態を確認 | なし（exit 1 = 誤り） |
| `adopt.py golden add／record／check／list` | 現状の挙動（終了コード・標準出力・標準エラー）を記録して再生する特性化テスト | `tests/system/golden/` |

手順の詳細（rd-author・test-designer・rd-auditor・implementer の役割）は skill `adopt-existing` にあります。

## 10.2 3 つの層（信頼度が違うものを混ぜない）

| 層 | 中身 | 作り手 | 信頼度 | 決定状態 |
|---|---|---|---|---|
| 1 事実 | 棚卸し（ファイル・ルート・テーブル・テスト・churn） | `scan`（決定的） | 高（コードの写し） | 要求ではない |
| 2 仮説 | 逆生成の要求・AC・質問票 | rd-author | 中（意図は推測） | 常に「承認待ち」・出自「逆生成」。**包括承認しない** |
| 3 固定 | 現状の挙動の golden master と既存テストの再利用 | test-designer | 高（実測）。ただし「正しい」ではなく「今こうである」 | 承認待ちの要求にも付けられる |

利用者が承認した要求だけが、通常の run の対象（変更の根拠）になります。

## 10.3 調査と、この toolkit への適合の検証

利用者の想定は「Adaption / Analytics / Rebuild を先に行い、データ層を整える」でした。公開されている知見を、次の 4 点で突き合わせました。

### 調査した方式

| 方式（出典） | 要点 | 採否 | 理由 |
|---|---|---|---|
| リバースエンジニアリングの分類（Chikofsky & Cross, 1990, *IEEE Software*） | 既存システムから、より抽象的な表現（設計・要求）を復元する「再文書化」と「設計の回復」を、改造（リエンジニアリング）と分けて扱う | **採用**（層 1・2） | 復元と改造を分ければ、承認前に実装を変えずに済む。EABK の「要求が正本」と同じ向き |
| 特性化テスト（Feathers, *Working Effectively with Legacy Code*, 2004）／承認テスト（golden master） | 正しさではなく現状の挙動を記録し、変更で意図しない差を検出する | **採用**（層 3） | 既存アプリには AC がなく、System Test を先に作れない。記録した現状を期待値にできる。Hyrum の法則（観察できる挙動は誰かが依存する）とも整合 |
| Strangler Fig（Fowler） | 新旧を並存させ、機能のまとまり単位で段階的に置き換える | **採用**（変更の run の方針） | 1 項目ずつ worktree・統合・検証する conductor の進め方と同型。「まとまり」が `--boundary` の単位になる |
| ホットスポット分析（Tornhill, *Your Code as a Crime Scene*, 2015） | 変更頻度 × 複雑さの高い所に、欠陥と変更が集まる | **採用**（回収の順序） | 全量を一度に回収しない（コスト・誤りの増加）ので、価値の高い所から。`scan` が churn × √行数 で並べる |
| 意思決定の記録（Nygard, ADR, 2011） | 決定を短い文書で残す | **既存の機構で足りる** | 決定記録（§9）・質問票・出典台帳が同じ役割 |
| LLM による要求・仕様の逆生成（2024〜2025 年の研究で報告） | コードから文章の要求・説明を生成できる。一方、存在しない要求の生成（幻覚）と欠落が課題で、自動の指標では信頼できず、人の確認と、元のコードへの根拠づけが要る。生成物から元を再構成して比べる方法（reverse generation）が提案されている | **採用（ただし拘束つき）** | 層 2 に、出典必須・証跡の固定（`anchor`）・承認待ち固定・独立監査での逆生成の整合の確認を課した |
| 全面の書き直し（Rebuild）を先に行う | 仕様を再構築してから作り直す | **先にはしない** | 過去の修正・暗黙の仕様が失われやすい。層 1〜3 が整って初めて、承認済みの要求と golden を満たす置換が検証できる（＝ Rebuild は層 3 の後に、まとまりごとに行える） |

### 適合の検証（この toolkit の目的に照らして）

| 目的・規則 | 方式が満たす根拠 | 検証（テスト） |
|---|---|---|
| 要求定義書の唯一の書き手は rd-author（G-1）、ID は `next-id.py` だけ（G-3） | `adopt.py` は要求定義書を編集せず、ID も振らない。書くのは棚卸し・証跡・golden・依頼文だけ | `tests/toolkit/test_adopt.py` |
| 要求と実装・テストの一貫性（出典・カタログ・台帳） | 逆生成の要求は SRC 必須。SRC には証跡の固定がないと承認できない。回収率はカタログと要求から計算 | `test_check_guards_reverse_generated_requirements` |
| 意図の取り違えを防ぐ（人の承認） | 逆生成は包括承認を `check` が拒否。承認は利用者の `<answers>` だけ | 同上 |
| 検証可能性（System Test は実装より前・実装者が書き換えない） | golden は `tests/system/` に置くので、implementer・reviewer は変更できない（G-2）。固定時に 2 回実行し、非決定なら記録を拒否 | `test_golden_rejects_nondeterministic` |
| 退行の防止 | `golden check` を台帳のケースにすれば、統合のたびに canary と同じ仕組みで実行される | `test_golden_record_check_and_regression` |
| 変更の最小コスト（Token・時間） | 棚卸しは LLM を使わない。依頼は 6 まとまり程度まで。hotspot 順 | `test_scan_inventory`・`test_request_draft_is_unapproved_and_scope_none` |
| 仮説の陳腐化の検出 | 証跡の範囲のハッシュ（空白は無視）が変わると DRIFT | `test_anchor_drift_and_whitespace_insensitive` |

### 限界（正直に）

- 逆生成の要求の質は、LLM とコードの読みやすさに依存します。独立監査（reverse generation の確認）で下げますが、ゼロにはなりません。だから承認を利用者に残しています。
- `scan` のルート・テーブルの検出は、主要なフレームワークの正規表現です。検出できない構成（動的ルーティングなど）は、棚卸しに出ません。出なかったことは、存在しないことの証明ではありません。「回収率」はカタログ・要求に書かれたパスの割合であって、意味の網羅ではありません。
- golden は、コマンドとして呼べる挙動（CLI・スクリプト・小さなドライバー）に向きます。画面操作や外部サービスを介する挙動は、通常の System Test（E2E）か manual にします。
- 設計書とコードが食い違うとき、どちらが正しいかは決めません。競合・質問票にして、利用者に返します。

## 10.4 設計書がある場合

`scan` が設計書の候補（設計・仕様・ADR・OpenAPI・ER 図などの名前のファイル）と、文書内の ID の接頭辞（`REQ-`・`FUNC-` など）を挙げます。rd-author は設計書を**先に**読み、次のように扱います。

- 設計書の記述は出典（区分: 設計書）。コードの記述は出典（区分: コード）。**両方**を引用できる要求が最も強い仮説です。
- 食い違いは競合か質問票。どちらかを黙って選ばない。
- 既存の ID は、出典に残し、EABK の ID（FR・AC）に置き換えません（対応は出典の欄で追える）。

## 10.5 運用

- 回収したまとまりは `docs/baseline/evidence.json` に残ります。コードを変更した後は `adopt.py check`（verify の外で実行。`--strict` は警告も失敗にする）で DRIFT を確認します。
- `docs/baseline/` と `tests/system/golden/` は git で管理します（チームで共有する）。
- `adopt.py scan` は何度でも実行できます（上書き）。基準の commit が HEAD と違えば、`check` が STALE を出します。
