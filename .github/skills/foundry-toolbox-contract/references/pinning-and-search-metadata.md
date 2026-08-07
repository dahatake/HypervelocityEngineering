# Pinning と検索メタデータ（TB-CAP-03 / TB-CAP-04）

Microsoft Learn 確認日 2026-08-04。

## 1. tool search の動作（前提）

toolbox の tools に `{"type": "toolbox_search"}` を含めると、初回の `tools/list` から
toolbox 内の全 Tool が隠れ、代わりに 2 つの meta-tool が公開される。

| meta-tool | 役割 |
|---|---|
| `tool_search(query, limit)` | 必要な能力を自然言語で述べ、該当 Tool 定義を受け取る |
| `call_tool(name, arguments)` | 発見した Tool を名前で呼び出す |

- ランキングは **BM25**（term frequency / IDF / 文書長正規化）。
- 索引対象は Tool 名・description・パラメータ情報（引数名と引数 description を**ネスト 3 階層**まで）。
- モデルは 1 ターン内で `tool_search` を何度でも呼べる。取得済み Tool はそのターン中ずっと呼び出せる。
- `toolbox_search` エントリ自体は `tools/list` に現れず、種別あたりの無名 Tool 上限にも数えない。

`call_tool` が必要な理由: 初回 `tools/list` に登録されていない Tool をモデルが直接呼ぼうとすると、
多くのランタイムが「未知の Tool」として防御する。`call_tool` は登録済みでポリシー適用可能な
ディスパッチ経路を提供する。

## 2. TB-CAP-03 `Pinning Policy`

### pin とは

`tool_configs` の `pin: true` を指定した Tool は、`tool_search` / `call_tool` と並んで
`tools/list` に常に現れる。検索のラウンドトリップなしで即座に呼べる。

`"*"` をキーにすると、その MCP server / 組み込み Tool エントリ内の全 Tool を pin できる。

### 何を pin するか

公式の指針は「検索は long tail のためのもの」。

> Search is for the long tail. It is not a good default for tools the model constantly needs.

pin すべき Tool:

- ポリシー Tool（承認・ガード・停止）
- 頻用データアクセス Tool
- モデルが再発見する必要のない中核契約 Tool

pin しない Tool（= 検索に載せる）:

- まれにしか使わないが必要なときは重要な Tool
  （資格情報のローテーション、失敗デプロイの復旧、コンプライアンス例外の適用、監査証跡の調査）

### prompt cache との関係

pin は決定的なので、prompt prefix が安定する。これが prompt cache の動作を保つ。
検索で毎回異なる Tool が前置されると prefix が変動しキャッシュが効きにくくなる。

### 自動 pin

Toolbox は利用頻度に応じて**ユーザー単位で自動 pin** する。warmup 期間の後に `tools/list` へ現れ、
利用が変われば古いエントリは外れる。開発者による手動 pin はこれに上乗せできる。

> warmup 期間と stale 判定の具体値は未公開。設計時に固定値を書かない。

### 記載例

```
- Status: selected
- Pinned tools: order-read, policy-check
- Pin rationale: 全ワークフローで初手に呼ぶ / 承認判定に必須のため検索経由にしない
- Unpinned scope: 監査照会・返金取消・データ削除など、月次以下の頻度で使う 18 Tool
- Wildcard pin: not used
- Checked at: 2026-08-04
```

## 3. TB-CAP-04 `Search Metadata`

### なぜ必要か

ベンチマークで tool search が失敗したのは、**Tool description が不揃い**なときだった。
実装詳細を書いていてユーザーの語彙を反映していない、あるいは
`get` / `create` / `manage` / `REST API` のように一般的すぎる description が原因。

`additional_search_text` は検索専用のテキストフィールドで、**モデルには渡らない**。
元 MCP server の Tool スキーマは変更されない。返却されるスキーマは綺麗なまま、
検索索引だけが別名・ドメイン用語・内部名称・ユーザー語彙を学習する。

### 効果（実測）

メタデータ調整後:

| 指標 | 改善 |
|---|---|
| 検索ヒット率 | 約 +56% |
| end-to-end 精度 | 約 +55% |
| 全 Tool 前渡しベースラインとの差 | 約 4% 以内まで回復 |

### 書き方

「利用者がその操作を呼ぶときに使う言葉」を列挙する。説明文を書かない。

| 悪い例 | 良い例 |
|---|---|
| `runs a query against the configured database` | `analytics query, dashboard data, SQL report, warehouse lookup, inspect tables` |
| `Tool for order management` | `注文照会, 受注状況, オーダー検索, 伝票番号, 出荷状況` |

日本語アプリでは**日本語と英語の両方**を入れる。モデルが英語で検索語を生成する場合があるため。

### 記載例（表）

| Tool ID | Pinned | Additional search text | 想定ユーザー語彙 |
|---|---|---|---|
| order-read | yes | （pin のため不要） | — |
| refund-cancel | no | `返金取消, リファンド撤回, refund reversal, chargeback undo` | 「返金を取り消したい」 |
| audit-trail-query | no | `監査証跡, 操作履歴, 誰がいつ, audit log, activity history` | 「誰が変更したか調べたい」 |
| segment-export | no | `deferred（実測後に追加）` | 未評価 |

### 初回設計では全件を埋めなくてよい

未 pin Tool が数十個ある設計で、全件の語彙を事前に推測して埋めるのは根拠のない作業になる。
公式指針も反復型である。

> 「inspect the misses. The first useful tuning pass probably won't be algorithmic. It will be editorial.」

- **初回**: 語彙が自明な Tool だけ埋め、残りは `deferred（実測後に追加）` と記す。
- **実測後**: 検索でヒットしなかった Tool は `additional_search_text` を**必須**にする。
- **行そのものが無い**のは初回でも不可。Tool 一覧としての網羅性は最初から必要。

## 4. よくある失敗

| 失敗 | 対処 |
|---|---|
| 全 Tool を pin して「安全側に倒す」 | tool search が無効化されるのと同じ。トークン削減が消える（R6） |
| `additional_search_text` に説明文を書く | 検索語彙にならない。モデルにも渡らないので説明としても無意味（R10） |
| 中核 Tool を pin せず検索に載せる | 毎ターン検索ラウンドトリップが増え、prompt cache も不安定になる |
| 日本語 Tool に日本語語彙だけ入れる | モデルが英語クエリを出すと外れる |
| description を直さず `additional_search_text` だけ足す | description はモデルの選択根拠でもある。両方直す |
