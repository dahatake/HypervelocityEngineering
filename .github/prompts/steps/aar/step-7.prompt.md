{root_ref}

{app_arch_scope_section}
## 目的
後付けした Agentic Retrieval を含めたアプリケーション全体を実際に動かし、
機能要件・非機能要件への適合を**測定で**判定する。

## なぜ必要か
Step.6 は `retrievalReasoningEffort` の比較に限定した測定であり、検索経路そのものの調整が目的である。
そのため「後付けした検索経路を含めて、アプリケーションが目標の応答時間・回答品質・コストを満たすか」は
確認されていない。既存アプリへの後付けでは、追加した検索経路が全体の目標を崩していないことの確認が要る。

## 入力
- `docs/catalog/app-catalog.md`
- `docs/azure/agentic-retrieval/{serviceId}-design.md`（Step.2 出力 — 目標値と閾値の根拠）
- `src/test/integration/agentic-retrieval/`（Step.4 出力 — 測定に再利用する既存テスト資産）

## 出力
- `docs/azure/agentic-retrieval/requirements-conformance-report.md`

## 測定要件
- 測定対象は **デプロイ済みの Knowledge Base とアプリケーションのエンドポイント**とする。本 Step のために Azure リソースを新規作成しない。
- 測定には Step.4 が生成した統合テスト資産を再利用する。
- 応答時間はパーセンタイル（p50 / p95 等）で記録し、どのパーセンタイルかを明示する。
- 設計成果物に数値目標が無い要件は `NO_TARGET` とし、実測値だけを残す。目標を推測で補わない。
- Step.6 が測る reasoning effort 別の指標を再測定しない。重複は Step.6 の結果を参照する。

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
- 測定のために Knowledge Base 構成・アプリケーション実装・デプロイ済みリソースを変更しない。

{existing_artifact_policy}

## Custom Agent
`QA-RequirementsConformanceEval` を使用

## 依存
- Step.6（Retrieval 実測評価）が `aar:done` であること

## 完了条件
- `docs/azure/agentic-retrieval/requirements-conformance-report.md` が作成されている
- 測定条件ラベル 8 件がすべて記載されている
- 測定表が 1 行以上あり、各行の判定が 4 値のいずれかである
- `Conclusion` / `Rationale` / `Simplification-Candidate` が記載されている
{completion_instruction}{app_id_section}{additional_section}
