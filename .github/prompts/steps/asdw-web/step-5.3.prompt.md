{root_ref}

{app_arch_scope_section}
## 目的
デプロイ済みの Web アプリと API を実際に動かし、機能要件・非機能要件への適合を**測定で**判定する。

## なぜ必要か
Step.5.1（WAF レビュー）と Step.5.2（整合性チェック）は設計文書と成果物の照合で完結する。
そのため「デプロイした構成が目標の応答時間・スループット・成功率を実際に満たすか」は確認されていない。
選んだ実行基盤が過剰かどうかも設計文書からは判定できず、目標値と実測値の差でしか評価できない。

## 入力
- リソースグループ名: `{resource_group}`
- `docs/catalog/app-catalog.md`
- `docs/azure/azure-architecture-review-report.md`（Step.5.1 出力 — 目標値と閾値の根拠）
- `docs/azure/dependency-review-report.md`（Step.5.2 出力）
- `src/test/e2e/playwright/`、`src/test/post-deploy/`、`src/test/integration/add-service/`（測定に再利用する既存テスト資産）

## 出力
- `docs/azure/requirements-conformance-report.md`

## 測定要件
- 測定対象は **デプロイ済みのエンドポイント**とする。本 Step のために Azure リソースを新規作成しない。
- 測定には当該ワークフローが既に生成したテスト資産を再利用する。Azure Load Testing 等の利用は任意。
- 応答時間は平均ではなくパーセンタイル（p50 / p95 等）で記録し、どのパーセンタイルかを明示する。
- 設計成果物に数値目標が無い要件は `NO_TARGET` とし、実測値だけを残す。目標を推測で補わない。

## 記録する指標
要件 ID / 種別（FR・NFR）/ 目標 / 閾値 / 実測値 / 判定 / 余裕度 / 証跡

## レポートの固定フォーマット（HVE artifact gate が機械検証）
- 測定条件: `Schema-Version` / `Workflow` / `Step` / `Agent` / `Measured-At` / `Target-Environment` / `Measurement-Tool` / `Secret-Redaction`
- 測定表: `| Req ID | Kind | Target | Threshold | Measured | Judgement | Headroom | Evidence |`（1 行以上必須）
- 判定語彙: `PASS` / `FAIL` / `NOT_MEASURED` / `NO_TARGET` の 4 値のみ
- 結論: `- Conclusion:` と `- Rationale:`
- 簡素化候補: `- Simplification-Candidate:`（該当なしは `none`）

## Azure 公式情報参照（Microsoft Learn MCP 必須）
- Azure サービス / CLI / SDK / SKU / メトリクス定義を扱う場合、**Microsoft Learn MCP が利用可能なら必ず参照**する。
- 参照した Microsoft Learn の **title / URL / 確認事項** を `{WORK}` の作業ログへ記録する。
- 利用できない場合は `要確認（Microsoft Learn MCP 未取得）` と記録し、**推測で確定しない**。

## 禁止事項
- 測定していない数値を書かない。実行できなかった指標は `NOT_MEASURED` と理由を記す。
- 実測値から逆算して目標・閾値を作らない。
- 目標が無いこと（`NO_TARGET`）と測れなかったこと（`NOT_MEASURED`）を同じ語彙へ畳み込まない。
- 測定のためにアプリケーション構成・インフラ定義・デプロイ済みリソースを変更しない。

{existing_artifact_policy}

## Custom Agent
`QA-RequirementsConformanceEval` を使用

## 依存
- Step.5.1（WAF アーキテクチャレビュー）と Step.5.2（整合性チェック）が `asdw-web:done` であること

## 完了条件
- `docs/azure/requirements-conformance-report.md` が作成されている
- 測定条件ラベル 8 件がすべて記載されている
- 測定表が 1 行以上あり、各行の判定が 4 値のいずれかである
- `Conclusion` / `Rationale` / `Simplification-Candidate` が記載されている
{completion_instruction}{app_id_section}{additional_section}
