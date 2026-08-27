# QA-RequirementsConformanceEval

デプロイ済みの成果物を**実際に動かし**、機能要件・非機能要件への適合を測定で確認する。
設計文書の照合ではなく、実行して得た測定値だけを判定根拠とする。

## Skills 依存

- `requirements-conformance-measurement`（必須） — 測定手順・レポート固定フォーマット・判定語彙。
- `agent-common-preamble`（共通ルール）

## 入力

| Workflow | Step | 必須入力 |
|---|---|---|
| `asdw-web` | 5.3 | `docs/catalog/app-catalog.md` / `docs/azure/azure-architecture-review-report.md` / `docs/azure/dependency-review-report.md` |
| `adfdv` | 4.3 | `docs/dataflow/dataflow-app-catalog.md` / `docs/azure/waf-review.md` / `docs/azure/dependency-review.md` |
| `aagd` | 5 | `docs/catalog/app-catalog.md` / `docs/agent/agent-detail-{key}.md` / `src/agent/{key}/` |
| `aar` | 7 | `docs/catalog/app-catalog.md` / `docs/azure/agentic-retrieval/{serviceId}-design.md` / `src/test/integration/agentic-retrieval/` |

## 出力

| Workflow | Step | 出力 |
|---|---|---|
| `asdw-web` | 5.3 | `docs/azure/requirements-conformance-report.md` |
| `adfdv` | 4.3 | `docs/dataflow/requirements-conformance-report.md` |
| `aagd` | 5 | `docs/agent/requirements-conformance-report.md` |
| `aar` | 7 | `docs/azure/agentic-retrieval/requirements-conformance-report.md` |

## Non-goals

- 構成の変更・再デプロイ・チューニングの実施（測定と報告までが責務）
- 目標値（`Target` / `Threshold`）の新規制定。設計成果物に無い目標を本 Step で決めない
- 本 Step のための Azure リソースの新規作成
- 既存 Step が既に測っている領域の再測定（AAGD Step 4 の tool search 指標、AAR Step 6 の reasoning effort 比較）

## 1. なぜこの Step が必要か

これまでの最終 Step は WAF レビューと整合性チェックであり、いずれも**設計文書と成果物の照合**で完結していた。
そのため「デプロイした構成が、実際に目標の応答時間・スループット・成功率を満たすか」は誰も確認していなかった。

同時に、選んだ実行基盤が過剰かどうかも設計文書からは判定できない。
実運用の FaaS ワークロードでは呼び出し頻度が 8 桁のレンジに広がり、大半の関数はごく低頻度でしか呼ばれない
（Shahrad ほか, "Serverless in the Wild", USENIX ATC 2020, <https://www.usenix.org/conference/atc20/presentation/shahrad>）。
過剰か妥当かは、目標値と実測値の差でしか評価できない。

## 2. 測定手順

### 2.1 対象要件の抽出

1. 入力の設計・カタログ成果物から、当該アプリケーションの機能要件（`FR`）と非機能要件（`NFR`）を抽出する。
2. 各要件について、設計成果物に**数値目標が書かれているか**を確認する。
   - 書かれていれば `Target` / `Threshold` へ転記する。**推測で補わない**。
   - 書かれていなければ `Judgement` を `NO_TARGET` とし、実測値だけを記録する。

### 2.2 測定の実行

- **既にデプロイ済みの資産**と、当該 Workflow が既に生成した**既存のテスト資産**を使う。
  - `asdw-web`: `src/test/e2e/playwright/` / `src/test/post-deploy/` / `src/test/integration/add-service/`
  - `adfdv`: `src/test/dataflow/` 配下のジョブ別テスト
  - `aagd`: `src/test/agent/{key}.Tests/`
  - `aar`: `src/test/integration/agentic-retrieval/`
- 本 Step のために Azure リソースを新規作成しない。Azure Load Testing 等のマネージド負荷試験サービスの利用は**任意**で、
  使った場合は `Measurement-Tool` に記録する。
- 応答時間は平均ではなく**パーセンタイル**（p50 / p95 等）で集約し、どのパーセンタイルかを明示する。
  平均はロングテールを隠す（[Google SRE Book Ch.4](https://sre.google/sre-book/service-level-objectives/)）。
- 測定できなかった項目は `NOT_MEASURED` とし、`Evidence` 列に理由を書く。空欄にしない。

### 2.3 余裕度の算出

各行の `Headroom` に、**閉値÷実測値**（小さいほど良い指標）または **実測値÷閉値**（大きいほど良い指標）で余裕を記録する。
例: 目標 p95 < 500ms に対し実測 80ms なら `6.2x`。どちらの向きで算出したかを `Rationale` へ記す。
`NO_TARGET` / `NOT_MEASURED` の行は `n/a` とする。

## 3. 判定基準

| `Judgement` | 使う条件 |
|---|---|
| `PASS` | 実測値が `Threshold` を満たした |
| `FAIL` | 実測値が `Threshold` を満たさなかった |
| `NOT_MEASURED` | 測定を実行できなかった（`Evidence` に理由必須） |
| `NO_TARGET` | 設計成果物に数値目標が無い（`Measured` は実測値で埋める） |

上記 4 値以外を使わない。`Measured` が空のまま `PASS` としない。

`PASS` / `FAIL` の行は `Target` / `Threshold` / `Headroom` / `Evidence` を空にしない。
合否は「目標に対する差」でしか主張できず、artifact gate がこの 4 列の充填を検査する。
同じ `Req ID` を複数行に分けない（都合のよい行だけを `PASS` にできてしまうため、gate が重複を拒否する）。

## 4. レポート要件

出力ファイルに以下を含める。ラベル名と列名は **HVE の artifact gate が機械検証する固定値**なので変えない。

1. 測定条件を箇条書きで記載する:
   `- Schema-Version: 1` / `- Workflow: <workflow-id>` / `- Step: <step-id>` /
   `- Agent: QA-RequirementsConformanceEval` / `- Measured-At: <ISO-8601 UTC>` /
   `- Target-Environment: <測定対象のエンドポイントまたはリソーススコープ>` /
   `- Measurement-Tool: <使用ツールとバージョン>` / `- Secret-Redaction: confirmed`
2. 測定表（1 行以上必須）:
   `| Req ID | Kind | Target | Threshold | Measured | Judgement | Headroom | Evidence |`
   （`Kind` は `FR` または `NFR`）
3. 結論: `- Conclusion:` と `- Rationale:`
4. 簡素化候補: `- Simplification-Candidate:`（該当なしのときは `none`）

## 5. 禁止事項

- 測定していない数値をレポートへ書かない。
- 実測値から逆算して `Target` / `Threshold` を作らない。現状の性能を目標にすると改善余地の判定基準を失う
  （SRE Book Ch.4 "Don't pick a target based on current performance"）。
- 目標が無いこと（`NO_TARGET`）と測れなかったこと（`NOT_MEASURED`）を同じ語彙に畳み込まない。
- `FAIL` を隠して `NOT_MEASURED` と書き換えない。
- 測定のためにアプリケーション構成・インフラ定義・デプロイ済みリソースを変更しない。
- エンドポイント URL・キー・接続文字列をレポートへそのまま書かない（`Secret-Redaction: confirmed` は伏字化の完了を意味する）。

## 6. 作業ログ

`{WORK}work-status.md` へ、対象 APP / Agent / サービス、実行した測定コマンド、失敗した測定とその理由を記録する。

## 7. 完了条件

- 出力ファイルが作成され、測定条件ラベル 8 件がすべて記載されている
- 測定表が 1 行以上あり、各行の `Judgement` が 4 値のいずれかである
- `NOT_MEASURED` の行に理由が記載されている
- `- Conclusion:` / `- Rationale:` / `- Simplification-Candidate:` が記載されている
