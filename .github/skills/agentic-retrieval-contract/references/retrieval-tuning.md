# Retrieval Tuning — AR-CAP-01 / AR-CAP-03

Microsoft Learn 確認日: 2026-08-04。tier 上限・region・API version は実行時に再確認する。

## 1. パイプラインの前提

Knowledge Base への 1 回の retrieve 要求は次の順で処理される。

1. **Workflow initiation** — アプリが query と会話履歴を渡す。
2. **Query planning** — `low` / `medium` では LLM がサブクエリを生成する。`minimal` ではこの段が省略され、Knowledge Source へ直接クエリが発行される。
3. **Query execution** — サブクエリが**全て同時に**実行される。keyword / vector / hybrid のいずれか。各サブクエリは semantic rerank を通り、citation 用の reference が抽出される。
4. **Result synthesis** — 結果を統合する。merged content は常に返る。source references と activity log は任意。

「最小限のクエリ回数で返す」とは、**アプリ側で検索を何度も呼ばないこと**（1 retrieve 要求に集約する）と、**その 1 要求内で生成されるサブクエリ数と LLM 処理量を抑えること**の 2 つを指す。前者は Knowledge Base に複数 Knowledge Source を束ねることで達成し、後者は retrieval reasoning effort で制御する。

## 2. AR-CAP-01 `Knowledge Base Contract`

`- ラベル: 値` の定型キー行で記載する。

| ラベル | 必須 | 値の条件 |
|---|---|---|
| `Status` | ✅ | `selected` または `N/A`。`N/A` のときは `Reason` / `Decision source` / `Recheck condition` を併記 |
| `Knowledge base name` | ✅ | 命名規則に従う実名。`TBD` は設計未確定として扱われ、Deploy は block |
| `Knowledge domain` | ✅ | この KB が担う知識ドメインを 1 文で |
| `Query planning LLM` | ✅ | `model-router` / `fixed` / `none`。`minimal` 固定で運用し、retrieve 要求での上書きを行わない場合は `none`。retrieve 要求で `low` / `medium` へ上書きする設計なら、上書き時に使う LLM を記載する |
| `Retrieval reasoning effort` | ✅ | `minimal` / `low` / `medium`。**本契約が正本**（AR-CAP-03 に重複記載しない） |
| `Effort rationale` | ✅ | latency / cost / 検索深度のトレードオフをどう判断したか |
| `Output mode` | ✅ | `extractiveData` / `answerSynthesis`。`minimal` のときは `extractiveData` 固定 |
| `Retrieval instructions` | ✅ | LLM の KS 選択・スキップを誘導する指示文。不要なら `none: <理由>` |
| `Knowledge source count` | ✅ | AR-CAP-02 の行数と一致する整数。2 以上 10 以下（R14 / R5） |
| `Index semantic configuration` | ✅ | どの semantic configuration を用いるか、またはどこで確定するか。各サブクエリが semantic rerank を通るため、ここで検索品質の上限が決まる。単語だけの `TBD` は不可 |
| `Region availability` | 条件付き | `medium` を選ぶ場合は必須。対象 region で利用可能か確認した結果 |
| `Design status` | ✅ | `supported` / `preview` / `limited-access` / `unavailable` / `unknown` |
| `Checked at` | ✅ | `YYYY-MM-DD` |
| `Decision source` | ✅ | 判断根拠となるリポジトリ内パスまたは公式資料 |

### reasoning effort の選び方

| Level | 挙動 | 使いどころ | 主な Limits |
|---|---|---|---|
| `minimal` | LLM によるクエリ計画を無効化。KB に列挙された全 KS へ直接 text / vector 検索を発行し、最良の passage を返す。クエリ拡張なし。挙動が予測可能 | 既存検索 API からの移行、クエリ計画を自前で持つ場合 | `outputMode` は `extractiveData` 必須 / answer synthesis と web knowledge 非対応 / KB あたり KS は最大 10 |
| `low` | **既定**。LLM によるクエリ計画と KS 選択を 1 パス実行。サブクエリを生成して選択 KS へファンアウトし、結果をマージ。answer synthesis を有効化できる | latency と処理深度のバランスを取る標準構成 | answer token 上限あり / KB あたり KS 上限あり（tier 依存）/ semantic ranking の対象文書数に上限 |
| `medium` | 初回検索の後、高精度 semantic classifier が追加処理の要否を判定。不十分なら**1 回だけ**クエリプランを見直して再検索する。リソース上限が緩和される。網羅性より関連性を最適化 | LLM 支援検索の有用性を最大化したい場合 | answer token 上限は low より大きい / 反復は 1 回のみ（追加の入力トークンが課金対象）/ **利用可能 region が限定される** |

### 設定箇所

`retrievalReasoningEffort` は Knowledge Base 定義に設定すると全クエリの既定値になり、retrieve 要求に設定するとクエリ単位で上書きできる。**クエリ単位の上書きを使う場合は、その条件を `Effort rationale` に書く。**

## 3. AR-CAP-03 `Retrieval Budget`

`- ラベル: 値` の定型キー行で記載する。

| ラベル | 必須 | 値の条件 |
|---|---|---|
| `Expected subqueries per request` | ✅ | 想定本数または想定レンジ。`minimal` のときは「KS 件数分の直接検索」と書く |
| `Retrieval token budget` | ✅ | 有限値。`無制限` / `unlimited` は不可 |
| `LLM token budget` | ✅ | 有限値。`minimal` のときは `0` |
| `Latency target p50` | ✅ | 有限値 |
| `Latency target p95` | ✅ | 有限値 |
| `Max runtime` | ✅ | retrieve 要求の最大実行時間 |
| `Max output size` | ✅ | 応答サイズ上限 |
| `Degradation policy` | ✅ | 予算超過・KS 部分失敗時にどう縮退するか。`Required for Done` の KS が落ちた場合の扱いを明記 |
| `Measurement method` | ✅ | 実測方法（どのログ / どの指標で確認するか） |

### 課金モデル

Agentic Retrieval は 2 サービスから課金される。

1. **Azure AI Search** — サブクエリ実行と semantic ranking で消費した retrieval token。
2. **Azure OpenAI** — LLM によるクエリ計画と answer synthesis の入出力 token。KB に割り当てたモデルの料金。

クラシック検索がクエリ単位課金なのに対し、Agentic Retrieval は **token 単位課金**である。したがって予算はクエリ本数ではなく token で積む。

**既定は free plan**（Azure AI Search 側）であり、課金は明示的に有効化する必要がある。
無効のままだと本番想定の負荷に耐えないため、AR-CAP-03 では free / billable のどちらを前提にしたかを記載する。

- 有効化/無効化手順: <https://learn.microsoft.com/azure/search/agentic-retrieval-how-to-enable-disable>
- 上限は**価格レベルと reasoning effort の両方**で変わる: <https://learn.microsoft.com/azure/search/search-limits-quotas-capacity#agentic-retrieval-limits>
- リージョン可用性は「Agentic retrieval」列で確認する: <https://learn.microsoft.com/azure/search/search-region-support#features-subject-to-regional-availability>

### コストとレイテンシを下げる設計手段

1. reasoning effort を下げて LLM 処理を減らす。
2. コンテンツを整理し、少ない source / 文書で必要な情報に到達できるようにする（要約表・キュレーション済みドキュメント等）。
3. 常に検索する必要のない KS は `alwaysQuery` を `false` にし、`retrievalInstructions` で選択を誘導する。
4. `Max runtime` / `Max output size` を設定して暴走を防ぐ。

### サブクエリ本数の制御

サブクエリ本数を直接指定する設定は無い。`minimal` 以外では、LLM が次の 3 つから本数を決める。

1. ユーザークエリ
2. 会話履歴
3. semantic ranker の入力制約

したがって本数を確実に固定したい場合は `minimal` を選ぶ。

## 4. 検索品質の前提（索引側）

reasoning effort をいくら調整しても、索引側の品質が上限を決める。設計時に次を確認する。

- semantic configuration は Agentic Retrieval の索引で**必須**。どのフィールドを優先しランキングに使うかを決める。
- scoring profile を既定として指定すると、対象フィールドを含むクエリで組み込みのブースト条件が働く。
- プレーンテキストは analyzer でトークン化を制御できる。
- 画像・マルチモーダルは image verbalization または OCR / 画像解析を skillset で行う。

これらは索引設計の責務であり、本 Skill は「決めたことを AR-CAP-01 の `Decision source` から追えること」だけを要求する。
