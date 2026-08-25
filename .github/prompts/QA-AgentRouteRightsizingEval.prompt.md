# QA-AgentRouteRightsizingEval

AI Agent が採用した検索経路を、**より安い経路と並べて実測**し、過剰でないかを判定する。
設計文書の照合ではなく、実行して得た測定値だけを判定根拠とする。

## Skills 依存

- `ai-agent-capability-contract`（必須） — AG-CAP-10 の評価契約と `references/search-routing.md` のコスト階段。
- `agent-common-preamble`（共通ルール）

## 入力

| Workflow | Step | 必須入力 |
|---|---|---|
| `aagd` | 6 | `docs/ai-agent-catalog.md` / `docs/agent/agent-detail-{key}.md` |

推奨入力:

- `docs/catalog/unstructured-data-catalog.md`（ADA 経由の場合のみ。比較候補の選定根拠）
- `src/test/agent/`（測定に再利用する既存テスト資産）
- `docs/agent/requirements-conformance-report.md`（Step.5 の実測値。応答時間の再測定を避けるため）

## 出力

| Workflow | Step | 出力 |
|---|---|---|
| `aagd` | 6 | `docs/agent/route-rightsizing-report.md` |

## Non-goals

- 経路の変更・再デプロイ・チューニングの実施（測定と推奨までが責務）
- Step.5（要件適合実測）が測る FR / NFR 適合の再測定
- Step.4（tool search 実測評価）が測るトークン削減率の再測定
- 本 Step のための Azure リソース新規作成の必須化

## 1. なぜこの Step が必要か

反復検索と推論を伴う検索経路は、単一クエリ検索やデータストア native 検索よりコストと応答時間が大きい。
にもかかわらず「その経路でなければ達成できなかった」ことは、**より安い経路を実際に動かして比べない限り示せない**。

Step.5 はデプロイ済み構成が目標を満たすかを測るが、別経路との比較は行わない。
そのため、目標を満たしていても「もっと安い経路で足りた」場合を検出できない。
AG-CAP-10 が「候補経路を 2 段以上実測しない評価は受理しない」と定めているのはこのためである。

## 2. 手順

1. `docs/agent/agent-detail-{key}.md` の Section 7.0 から**採用した経路**を読む。
2. Skill `ai-agent-capability-contract` の `references/search-routing.md` §4.1 のコスト階段で、採用経路が何段目かを決める。
3. **採用段より安い段を最低 1 つ**選ぶ。`docs/catalog/unstructured-data-catalog.md` がある場合は「第2候補」「除外した経路と理由」を優先して選ぶ。
4. 評価データセットを固定する。件数と作り方をレポートへ書く。全段で同一データセットを使う。
5. 各段を実行し、**正答率（criterion pass rate）/ 1 リクエストあたりのトークン / 応答時間**を測る。
6. 比較表と結論をレポートへ書く。

## 3. 判定語彙（4 値固定）

| 値 | 意味 |
|---|---|
| `KEEP` | 安い段では要件を満たせず、採用段が妥当 |
| `DOWNGRADE` | 安い段でも要件を満たし、採用段は過剰 |
| `INSUFFICIENT` | 比較が 1 段しかできず、判定できない |
| `NOT_MEASURED` | 当該段を実行できなかった（理由必須） |

## 4. レポートの固定フォーマット

HVE の artifact gate が機械検証する。

- 測定条件: `Schema-Version` / `Workflow` / `Step` / `Agent` / `Measured-At` / `Dataset` / `Dataset-Size` / `Secret-Redaction`
- 比較表: `| Rung | Route | Accuracy | Tokens | Latency | Judgement | Evidence |`（**2 行以上必須**）
- 結論: `- Conclusion:`（上記 4 値のいずれか）と `- Rationale:`
- 推奨経路: `- Recommended-Route:`

## 5. 禁止事項

- 実測していない段の数値を書かない。実行できなかった段は **`NOT_MEASURED` の行として比較表に残し**、行ごとに理由を `Evidence` へ記す。
- 採用段の結果だけを載せて「適正」と結論しない（1 行の比較表は受理されない）。
- 段ごとに異なる評価データセットを使わない。
- 測定のために Agent 実装・設定・デプロイ済みリソースを恒久的に変更しない。
- 本番データを redact なしで使わない。

## 6. 完了条件

- `docs/agent/route-rightsizing-report.md` が作成されている
- 測定条件ラベル 8 件がすべて記載されている
- 比較表が 2 行以上あり、各行の判定が 4 値のいずれかである
- `Conclusion` / `Rationale` / `Recommended-Route` が記載されている
