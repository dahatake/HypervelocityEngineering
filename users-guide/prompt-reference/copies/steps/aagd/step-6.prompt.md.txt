{root_ref}

{app_arch_scope_section}
## 目的
AG-CAP-10 に従い、Agent が採用した検索経路が目的に対して過剰でないかを **2 段以上の比較実測**で判定する。

## なぜ必要か
Agentic Retrieval のように反復検索と推論を伴う経路は、単一クエリ検索やデータストア native 検索より
コストと応答時間が大きい。にもかかわらず「その経路でなければ達成できなかった」ことは、
より安い経路を実際に動かして比べない限り示せない。
Step.5（要件適合実測）はデプロイ済み構成が目標を満たすかを測るが、別経路との比較は行わない。

## 入力
- `docs/ai-agent-catalog.md`（Agent 一覧 — 測定対象の定義元）
- `docs/agent/agent-detail-{key}.md`（Section 7.0 の採用経路と Section 7.9 の評価契約）
- `docs/catalog/unstructured-data-catalog.md`（ADA 経由の場合のみ。資産ごとの検索経路候補と除外理由）
- `src/test/agent/`（測定に再利用する既存テスト資産）

## 出力
- `docs/agent/route-rightsizing-report.md`

## 測定要件
- 比較する経路は Skill `ai-agent-capability-contract` の `references/search-routing.md` §4.1 のコスト階段から選ぶ。
  **採用段と、それより安い段を最低 1 つ**の合計 2 段以上を実測する。
- 各段で同じ評価データセットと同じ判定基準を使う。データセットが違う結果を比較しない。
- 記録する指標は最低限、**正答率（または criterion pass rate）/ 1 リクエストあたりのトークン / 応答時間**の 3 つ。
- 本 Step のために Azure リソースを新規作成することを必須にしない。安い段が既存資産で測れない場合は
  `NOT_MEASURED` と理由を記し、推測値で埋めない。
- 未実測を `PASS` として扱わない。実行できなかった段も **`NOT_MEASURED` の行として比較表に残す**（比較表は 2 行以上必須で、行を落とすと成果物が拒否される）。その場合の `Conclusion` は `INSUFFICIENT` とする。

## レポートの固定フォーマット（HVE artifact gate が機械検証）
- 測定条件: `Schema-Version` / `Workflow` / `Step` / `Agent` / `Measured-At` / `Dataset` / `Dataset-Size` / `Secret-Redaction`
- 比較表: `| Rung | Route | Accuracy | Tokens | Latency | Judgement | Evidence |`（2 行以上必須）
- 判定語彙: `KEEP` / `DOWNGRADE` / `INSUFFICIENT` / `NOT_MEASURED` の 4 値のみ
- 結論: `- Conclusion:`（判定語彙と同じ 4 値）と `- Rationale:`
- 推奨経路: `- Recommended-Route:`

## 禁止事項
- 実測していない段の数値を書かない。
- 採用段の結果だけを載せて「適正」と結論しない。
- 比較のために本番データを退避なしで使わない。secret と個人データは redact する。
- 測定のために Agent 実装・設定・デプロイ済みリソースを恒久的に変更しない。

{existing_artifact_policy}

## Azure 公式情報参照（Microsoft Learn MCP 必須）
- Azure サービス / CLI / SDK / SKU / メトリクス定義を扱う場合、**Microsoft Learn MCP が利用可能なら必ず参照**する。
- 参照した Microsoft Learn の **title / URL / 確認事項** を `{WORK}` の作業ログへ記録する。
- 利用できない場合は `要確認（Microsoft Learn MCP 未取得）` と記録し、**推測で確定しない**。

## Custom Agent
`QA-AgentRouteRightsizingEval` を使用

## 依存
- Step.3（AI Agent Deploy）が `aagd:done` であること

## 完了条件
- `docs/agent/route-rightsizing-report.md` が作成されている
- 測定条件ラベル 8 件がすべて記載されている
- 比較表が 2 行以上あり、各行の判定が 4 値のいずれかである
- `Conclusion` / `Rationale` / `Recommended-Route` が記載されている
{completion_instruction}{app_id_section}{additional_section}
