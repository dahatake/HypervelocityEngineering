# QA-ToolSearchEval

デプロイ済みの Toolbox に対して tool search の on / off を実測比較し、
TB-CAP-02 の判定が妥当だったかを**測定で**裏付ける。

## Skills 依存

- `foundry-toolbox-contract`（必須） — TB-CAP-01〜05 と公式の制約。
- `agent-common-preamble`（共通ルール）

## 入力

| パス | 必須 | 用途 |
|---|---|---|
| `docs/agent/agent-detail-{key}.md` | 必須 | TB-CAP-01〜05 の設計値 |
| `src/agent/{key}/` | 必須 | 評価クエリの再利用元 |
| `docs/catalog/app-catalog.md` | 推奨 | APP-ID スコープ解決 |

## 出力

- `docs/agent/tool-search-eval/{key}-eval-report.md`

## Non-goals

- Toolbox / Tool の作成・変更（`Dev-Microservice-Azure-AgentDeploy` の責務）
- Tool description の書き換え（本 Step は測定と提案まで）
- 検索ランキングアルゴリズムの変更

## 1. なぜこの Step が必要か

公開されているトークン削減率（50 Tool で 60% 超、1,000 Tool で 97% 超）は
ToolRet ベンチマーク（44,000+ tools / 7,000 queries）の値であり、
**自社カタログの Tool 記述品質に依存する**。

description が不揃いなカタログでは検索が正しい Tool を返さず、
トークンは減っても end-to-end 精度が落ちる。導入効果は実測でしか判断できない。

## 2. 測定手順

### 2.1 評価クエリ集合

- 最低 10 件。以下を必ず含める。
  - 1 つの Tool で完結するタスク
  - **複数 Tool の組み合わせが必要なタスク**（最低 3 件）
  - 実行すべき Tool が存在しないタスク（過剰呼び出しの検出用）
- 各クエリに**期待 Tool 集合**を事前に記録する。
- クエリ集合はレポートへ全文を記載し、再現可能にする。

### 2.2 比較する条件

同一の Toolbox・同一クエリ集合に対し、tool search の on / off だけを変える。

- **off**: 全 Tool 定義を毎ターン渡す（ベースライン）
- **on**: `{"type": "toolbox_search"}` を有効化。pin と `additional_search_text` は設計値どおり

prompt caching は既定で有効。ベースラインでも有効のまま測る（無効化して比較しない）。

### 2.3 記録する指標

| 指標 | 取得方法 |
|---|---|
| 初期 `tools/list` のトークン数 | クライアント実測 |
| 1 ターンあたりの総入力トークン | 実測 |
| Tool 選択正解率 | 期待 Tool 集合との一致 |
| `tool_search` 呼び出し回数 | 実測 |
| 追加レイテンシ（p50 / p95） | 検索ラウンドトリップ分 |
| 過剰呼び出し率 | 該当 Tool が無いタスクで Tool を呼んだ割合 |

## 3. 判定基準

| 観測 | 判定 |
|---|---|
| トークン削減 20% 未満 | Tool 数が閾値付近すぎるか description が不揃い。`additional_search_text` を整備して再測定 |
| 正解率がベースラインより 10% 以上低下 | pin 対象を見直す。中核 Tool が検索に載っている可能性 |
| 特定 Tool が繰り返し外れる | その Tool の description と `additional_search_text` を改善対象として列挙 |
| いずれも問題なし | TB-CAP-02 の判定を妥当と結論づける |

## 4. レポート要件

`docs/agent/tool-search-eval/{key}-eval-report.md` に以下を含める。ラベルと列名は **HVE の artifact gate が機械検証する固定値**なので変えない。

1. 測定条件を箭印リストで記載する: `Toolbox name` / `Toolbox version` / `Total tools` / `Pinned tools` / `limit` / `Measured at` / `SDK / API version`
2. 評価クエリ表: `| Query ID | Query | Expected tools | Multi tool |`（`Multi tool` は `yes` / `no`）
3. 指標表: `| Metric | Measured off | Measured on | Evidence |`
4. **TB-CAP-02 の判定に対する結論**: `- Conclusion:` と `- Rationale:` を記載する（変更を推奨する場合は推奨値と根拠）
5. 検索で外れた Tool の一覧と、推奨する `additional_search_text`
6. 実測できなかった指標は on / off 両列を「未測定（理由）」と明記する。空欄にしない
7. `Evidence` 列には実測の出所（クライアント trace 等）を書く。公開ベンチマーク名を実測の出所にしない

## 5. 禁止事項

- 測定していない数値をレポートへ書かない。
- **公開ベンチマークの数値を自社の実測値として引用しない**。
- 設計書と実測が食い違う場合に、設計書へ合わせて実測値を丸めない。
- 精度が落ちたことを隠して「トークンが減った」だけを報告しない。両方を並記する。

## 6. 作業ログ

`{WORK}work-status.md` へ、対象 Agent ID・測定実施可否・失敗した測定とその理由を記録する。
TB-CAP-01〜05 を持たない Agent が対象の場合も、**成果物を省略しない**。
`docs/agent/tool-search-eval/{key}-eval-report.md` を作成し、`- Status: N/A` と
`- Reason:` / `- Decision source:` / `- Recheck condition:` を記載した理由付き N/A レポートを残す。

## 7. 完了条件

- Toolbox を持つ Agent: 評価クエリが 10 件以上あり、うち 3 件以上が複数 Tool の組み合わせを要する
- tool search の on / off 両方で全クエリを測定した
- 指標一覧表が埋まっている（未測定は「未測定（理由）」と明記）
- `Conclusion` と `Rationale` が記載されている
- Toolbox を持たない Agent: 理由付き N/A レポートが作成されている
