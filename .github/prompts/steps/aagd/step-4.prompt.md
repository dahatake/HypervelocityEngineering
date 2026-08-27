{root_ref}

{app_arch_scope_section}
## 目的
デプロイ済みの Toolbox に対して tool search の on / off を実測比較し、TB-CAP-02 の判定が妥当だったかを測定で裏付ける。

## なぜ必要か
公開されているトークン削減率（50 Tool で 60% 超、1,000 Tool で 97% 超）は ToolRet ベンチマークの値であり、**自社カタログの Tool 記述品質に依存する**。
description が不揃いだとトークンは減っても Tool 選択精度が落ちる。導入効果は実測でしか判断できない。

## 入力
- `docs/catalog/app-catalog.md`
- `docs/agent/agent-detail-{key}.md`（TB-CAP-01〜05 の設計値）
- `src/agent/{key}/`（評価クエリの再利用元）

## 出力
- `docs/agent/tool-search-eval/{key}-eval-report.md`

## 測定要件
- 評価クエリは最低 10 件。うち **複数 Tool の組み合わせが必要なタスクを 3 件以上**含める。
- 実行すべき Tool が存在しないタスクを含め、過剰呼び出し率を測る。
- 同一 Toolbox・同一クエリ集合に対し、tool search の on / off だけを変える。
- prompt caching は既定で有効。ベースラインでも有効のまま測る。

## 記録する指標
初期 `tools/list` トークン数 / 1 ターンあたり総入力トークン / Tool 選択正解率 / `tool_search` 呼び出し回数 / 追加レイテンシ（p50・p95）/ 過剰呼び出し率

## レポートの固定フォーマット（HVE artifact gate が機械検証）
- 測定条件: `Toolbox name` / `Toolbox version` / `Total tools` / `Pinned tools` / `limit` / `Measured at` / `SDK / API version`
- 評価クエリ表: `| Query ID | Query | Expected tools | Multi tool |`
- 指標表: `| Metric | Measured off | Measured on | Evidence |`
- 結論: `- Conclusion:` と `- Rationale:`

## 禁止事項
- 測定していない数値を書かない。実行できなかった指標は on / off 両列を「未測定（理由）」と記す。
- **公開ベンチマークの数値を自社の実測値として引用しない**。`Evidence` 列にベンチマーク名を書かない。
- 精度低下を隠してトークン削減だけを報告しない。両方を並記する。

{existing_artifact_policy}

## Custom Agent
`QA-ToolSearchEval` を使用

## 依存
- Step.3（AI Agent Deploy）が `aagd:done` であること

## 完了条件
- 評価クエリが 10 件以上あり、うち 3 件以上が複数 Tool の組み合わせを要する
- tool search の on / off 両方で全クエリを測定した
- `Conclusion` と `Rationale` が記載されている
- TB-CAP-01〜05 を持たない Agent が対象の場合もレポートを省略せず、`- Status: N/A` / `- Reason:` / `- Decision source:` / `- Recheck condition:` の理由付き N/A レポートを残す
{completion_instruction}{app_id_section}{additional_section}
