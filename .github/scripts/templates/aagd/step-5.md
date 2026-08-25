{root_ref}

{app_arch_scope_section}
## 目的
デプロイ済みの AI Agent を実際に動かし、機能要件・非機能要件への適合を**測定で**判定する。

## なぜ必要か
Step.4（tool search 実測評価）は Toolbox の tool search on / off に限定した測定であり、
`--enable-tool-search no` のときは実行対象から外れる。
そのため「デプロイした Agent がアプリケーションとして目標の応答時間・成功率・コストを満たすか」は
どの Step でも確認されていない。選んだ実行構成が過剰かどうかも目標値と実測値の差でしか評価できない。

## 入力
- `docs/catalog/app-catalog.md`
- `docs/ai-agent-catalog.md`（Agent 一覧 — 測定対象の定義元）
- `docs/agent/agent-detail-{key}.md`（AG-CAP の設計値と目標値の根拠）
- `src/test/agent/`（測定に再利用する既存テスト資産）

## 出力
- `docs/agent/requirements-conformance-report.md`

## 測定要件
- 測定対象は **デプロイ済みの Agent エンドポイント**とする。本 Step のために Azure リソースを新規作成しない。
- 測定には当該ワークフローが既に生成したテスト資産を再利用する。
- 応答時間はパーセンタイル（p50 / p95 等）で記録し、どのパーセンタイルかを明示する。
- 設計成果物に数値目標が無い要件は `NO_TARGET` とし、実測値だけを残す。目標を推測で補わない。
- Step.4 が測る tool search 指標（トークン削減率・Tool 選択正解率）を再測定しない。重複は Step.4 の結果を参照する。

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
- 測定のために Agent 実装・設定・デプロイ済みリソースを変更しない。

{existing_artifact_policy}

## Custom Agent
`QA-RequirementsConformanceEval` を使用

## 依存
- Step.3（AI Agent Deploy）が `aagd:done` であること

## 完了条件
- `docs/agent/requirements-conformance-report.md` が作成されている
- 測定条件ラベル 8 件がすべて記載されている
- 測定表が 1 行以上あり、各行の判定が 4 値のいずれかである
- `Conclusion` / `Rationale` / `Simplification-Candidate` が記載されている
{completion_instruction}{app_id_section}{additional_section}
