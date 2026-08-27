{root_ref}

{app_arch_scope_section}
## 目的
デプロイ済みの Knowledge Base に対して `retrievalReasoningEffort` を実測比較し、設計書の選択が妥当かを**測定で**判定する。

## なぜ必要か
reasoning effort は recall・token 消費・レイテンシのトレードオフであり、測定なしに正しい値は決められない。
「最小限のクエリ回数で結果を返す」という要件を、推測ではなく実測で裏付ける唯一の Step。

## 入力
- `docs/catalog/app-catalog.md`
- `docs/azure/agentic-retrieval/{serviceId}-design.md`（Step.2 出力）
- `src/test/integration/agentic-retrieval/`（Step.4 出力 — 評価クエリの再利用元）

## 出力
- `docs/azure/agentic-retrieval/{serviceId}-eval-report.md`

## 測定要件
- 評価クエリは最低 10 件。うち **Knowledge Source 横断が必要な質問を 3 件以上**含める。
- 答えが存在しない質問を含め、空振り率を測る。
- `minimal` と `low` を必ず比較する。`medium` は設計書がリージョン可用性を確認済みの場合のみ。
- `minimal` は `outputMode=extractiveData` 固定・answer synthesis / web KS 不可。その制約下で測る。

## 記録する指標
KS 到達率 / retrieve 呼び出し回数 / サブクエリ数 / 検索トークン / LLM トークン / レイテンシ（p50・p95）/ 空振り率

## 禁止事項
- 測定していない数値を書かない。実行できなかった指標は「未測定（理由）」と記す。
- 公式ドキュメントの一般論だけで effort を推奨しない。必ず本 Step の実測値を根拠にする。
- 設計書と実測が食い違うとき、設計書に合わせて実測値を丸めない。

{existing_artifact_policy}

## Custom Agent
`QA-AgenticRetrievalEval` を使用

## 依存
- Step.5（Agentic Retrieval Deploy）が `aar:done` であること

## 完了条件
- 評価クエリが 10 件以上あり、うち 3 件以上が Knowledge Source 横断である
- `minimal` と `low` の両方で全クエリを測定した
- 設計書の effort 選択に対する判定と根拠が記載されている
{completion_instruction}{app_id_section}{additional_section}
