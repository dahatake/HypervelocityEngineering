# QA-AgenticRetrievalEval

デプロイ済みの Knowledge Base に対して `retrievalReasoningEffort` を実測比較し、
設計書が選んだ値の妥当性を根拠づける。

## Skills 依存

- `agentic-retrieval-contract`（必須） — AR-CAP-01〜05 と reasoning effort の公式制約。
- `agent-common-preamble`（共通ルール）

## 入力

| パス | 必須 | 用途 |
|---|---|---|
| `docs/azure/agentic-retrieval/{serviceId}-design.md` | 必須 | 設計値（effort / KS / 予算） |
| `src/test/integration/agentic-retrieval/` | 必須 | 評価クエリの再利用元 |
| `docs/catalog/app-catalog.md` | 推奨 | APP-ID スコープ解決 |

## 出力

- `docs/azure/agentic-retrieval/{serviceId}-eval-report.md`

## Non-goals

- Knowledge Base / Knowledge Source の作成・変更
- インデックス定義やベクトル設定の変更
- モデルのファインチューニング

## 1. なぜこの Step が必要か

`retrievalReasoningEffort` は recall・token 消費・レイテンシのトレードオフであり、
**測定なしに正しい値は決められない**。本 Step は「最小限のクエリ回数で結果を返す」
という要件を、推測ではなく実測で裏付ける。

## 2. 測定手順

### 2.1 評価クエリ集合の準備

- 最低 10 件。以下の 3 種を必ず含める。
  - 単一 Knowledge Source で完結する質問
  - **複数 Knowledge Source の横断が必要な質問**（最低 3 件）
  - 意図的に答えが存在しない質問（過剰生成の検出用）
- 各クエリに期待される Knowledge Source 集合を事前に記録する。
- クエリ集合はレポートへ全文を記載し、再現可能にする。

### 2.2 比較する条件

`minimal` と `low` を必ず比較する。`medium` は設計書がリージョン可用性を確認済みの場合のみ追加する。

- `minimal` は LLM によるクエリプランニングを行わないため `outputMode` は `extractiveData` 固定。
  answer synthesis・web Knowledge Source は使えない。この制約下で測ること。
- 同一クエリ集合・同一 Knowledge Base に対して、effort だけを変えて測定する。

### 2.3 記録する指標

| 指標 | 取得方法 |
|---|---|
| KS 到達率 | 返却された references / activity log の KS 集合 ÷ 期待 KS 集合 |
| retrieve 呼び出し回数 | クライアント側の実測（1 であるべき） |
| サブクエリ数 | activity log |
| 検索トークン | activity log |
| LLM トークン（プランニング + 合成） | activity log |
| レイテンシ | クライアント実測（p50 / p95） |
| 空振り率 | 答えが存在しない質問で結果を返してしまった割合 |

## 3. レポート要件

`{serviceId}-eval-report.md` に以下を含める。

1. 測定条件（KB 名・KS 一覧・リージョン・測定日時・SDK/API バージョン）
2. 評価クエリ全文と期待 KS 集合
3. effort ごとの指標一覧表
4. **設計書の effort 選択に対する判定**: 妥当 / 変更を推奨（変更する場合は推奨値と根拠）
5. 実測できなかった指標は「未測定」と明記する（推定値で埋めない）

## 4. 禁止事項

- 測定していない数値をレポートへ書かない。実行できなかった場合は「未測定（理由）」と記す。
- 公式ドキュメントの一般論のみで effort を推奨しない。必ず本 Step の実測値を根拠にする。
- 設計書と実測が食い違う場合に、設計書へ合わせて実測値を丸めない。

## 5. 作業ログ

`{WORK}work-status.md` へ、対象サービス ID・測定実施可否・失敗した測定とその理由を記録する。
対象サービスが 0 件の場合は「対象なし」と明記し、成果物なしで完了する。

## 6. 完了条件

- 評価クエリが 10 件以上あり、うち 3 件以上が Knowledge Source 横断である
- `minimal` と `low` の両方で全クエリを測定した
- 指標一覧表が埋まっている（未測定は「未測定」と明記）
- 設計書の effort 選択に対する判定と根拠が記載されている
