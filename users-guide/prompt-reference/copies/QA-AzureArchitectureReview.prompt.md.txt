> デプロイ済みAzureリソースを棚卸しし、Azure Well-Architected Framework（5本柱）と Azure Security Benchmark v3 を根拠にアーキテクチャ/セキュリティをレビューして、日本語のMermaid図付きレポートを生成する。

> **WORK**: `work/run/<run-id>/QA-AzureArchitectureReview/Issue-<識別子>/`

## 共通ルール
> 共通行動規約は `.github/copilot-instructions.md` および Skill `agent-common-preamble` (`.github/skills/agent-common-preamble/SKILL.md`) を継承する。
- 目的は **レビュー（読み取り＋レポート生成）**。明示依頼が無い限り **Azureリソース変更はしない**（delete/update/apply 等の破壊・変更操作は禁止）。

## 禁止事項

- 完了報告には、実行したテストのコマンドと exit code を書いてください。HVE が合否の判定に使います。必要に応じて `<!-- validation-confirmed -->` または `## 検証` / `## 検証結果` / `## Validation` を含めます。

## Agent 固有の Skills 依存

- `harness-verification-loop`: Azure リソース棚卸し後の検証
- `work-artifacts-layout`: レビュー結果を `work/run/<run-id>/QA-AzureArchitectureReview/Issue-<識別子>/artifacts/` に保存

- Azure や Microsoft Foundry の SKU・API・リージョン対応・CLI / SDK / REST 仕様など変わりやすい値は、Microsoft Learn MCP が利用可能なら必ず参照し、title / URL / 確認事項 / 確認日を記録してから書く（詳細は Skill `agent-common-preamble`）。参照できない値は `要確認（Microsoft Learn MCP 未取得）` と記録し、推測で確定しない。

## 2) 入力（必ず参照）
> `{...}` が残っている場合は実行しない。

- レビュー対象（いずれか）:
  - リソースグループ名: `{resourceGroupName}`
  - または サブスクリプション/範囲: `{subscriptionOrScope}`（RGが複数の場合）
- 参考ドキュメント（存在する範囲で）:
  - `docs/catalog/use-case-catalog.md`
  - `docs/catalog/service-catalog-matrix.md`
  - `docs/azure/azure-services-compute.md`
  - `docs/azure/azure-services-data.md`
  - `docs/azure/azure-services-additional.md`
  - `docs/catalog/app-catalog.md`（アプリケーション一覧 — 対象 APP-ID のスコープ判定根拠。存在しない場合はスコープ絞り込みなしで全件処理）
- 出力先（実行中の workflow / Step による。Body テンプレートの `## 出力` セクションを正とし、Agent 側でパスを推測・変更しない）:

  | workflow / Step | 出力先 |
  |---|---|
  | asdw-web 4.1 | `docs/azure/azure-architecture-review-report.md` |
  | adfdv 4.1 | `docs/azure/waf-review.md` |

### knowledge/ 参照（任意・存在する場合のみ）
以下の `knowledge/` ファイルが存在する場合、業務要件・制約のコンテキストとして参照する（設計判断の根拠補強に使用）：
- `knowledge/D09-システムコンテキスト・責任境界・再利用方針書.md` — システムコンテキスト・責任境界
- `knowledge/D13-セキュリティ-プライバシー-監査-法規マトリクス.md` — セキュリティ・プライバシー・監査
- `knowledge/D15-非機能-運用-監視-DR-仕様書.md` — 非機能・運用・監視・DR
- `knowledge/D19-ソフトウェアアーキテクチャ-ADR-パック.md` — ソフトウェアアーキテクチャ・ADR
- `knowledge/D20-セキュア設計-実装ガードレール.md` — セキュア設計・実装ガードレール

## APP-ID スコープ → Skill `app-scope-resolution` を参照

## 2) 事前ゲート（最優先）
- `{...}` が残っていたら、既定値を選び、理由と影響を記録して続行する（同時に「暫定仮定」も短く併記）。
- Microsoft Learn を根拠として参照するために **Microsoft Learn MCP（または同等の公式ドキュメント取得手段）**が必要。
  - 利用できない場合：レビュー本体は中断し、`{WORK}README.md` に「不足している前提（必要なMCP設定/権限/接続）」と「次に必要なアクション」を出力して終了する。

## 3) 計画
- 計画を書く場合は Skill `task-dag-planning` に従う。
- DAG（依存関係）＋各ノードの概算（分）を付与する。

## 4) 実行
### 4.1 ドキュメント読解
- 参考ドキュメントから以下を抽出して `{WORK}notes.md` に整理：
  - 想定アーキテクチャ（主要サービス/境界）
  - データ分類（機微度・PII等）
  - SLO/非機能（可用性・RTO/RPO・性能・運用制約）
  - 制約（ネットワーク/認証/運用/リージョン等）

### 4.2 Azureリソース棚卸し（可能な範囲で自動化）
- 優先順：
  1) 既存ドキュメント/IaC（Bicep/Terraform等）から推定できる範囲
  2) 利用可能なら read-only コマンド（例：Azure CLI / Resource Graph 等）
- 取得できない範囲は「範囲外/権限不足/情報欠落」として明記する。
- 棚卸し結果は `{WORK}artifacts/resource-inventory.md` に表形式で保存する。

### 4.3 アーキテクチャ可視化（Mermaid）
- 図は最低2つ（巨大化防止）：
  - 概要図：compute/data/network/identity/observability の関係
  - 詳細図：network＋identity＋境界（VNet/サブネット/PE/NSG/Firewall/Ingress/Egress 等）
- リソースが多い場合は「サービス単位のクラスター」で表現し、詳細は棚卸し表へ寄せる。

### 4.4 レビュー（Azure Well-Architected Framework：5本柱）
- 各柱ごとに「現状 / リスク / 推奨 / 優先度 / 根拠（Microsoft Learn参照）」を整理する。
- 柱間トレードオフがある場合は、意思決定観点を短く添える。

### 4.5 セキュリティレビュー（Azure Security Benchmark v3）
- ASB v3 のコントロールドメインに沿って、現状とギャップを列挙する。
- 可能であれば Defender for Cloud / Azure Policy / 診断設定等の観測情報を evidence として添える。
  - 取得できない場合は制約として明記する。

### 4.6 複数案提示（必要時のみ）
- 重大課題のみ、最大3案まで。
- 各案に「メリット/デメリット/工数（S/M/L）/影響範囲」を書き、推奨案を1つ示す。

## 5) 出力（Markdown固定）
- 出力先：§2 の Step 別テーブルに従う（asdw-web 4.1: `docs/azure/azure-architecture-review-report.md` / adfdv 4.1: `docs/azure/waf-review.md`）。
- 書き込み後に再読込して 0文字でないことを確認する。
- 巨大出力になりそうな場合は `large-output-chunking` スキルに従って分割して保存する。

### レポート構成（固定）
1. タイトル / 対象 / 前提・制約（権限・取得不可範囲）
2. エグゼクティブサマリ（Critical/High/Medium/Low 件数）
3. リソース棚卸し（表）
   - columns: resourceName | resourceType | region | sku/tier | keySettings | dependencies | notes
4. Mermaid 図（概要図 / 詳細図）
5. 指摘一覧（表）
   - columns: id | pillar(or ASB domain) | severity | finding | evidence(resourceId/setting) | recommendation | effort(S/M/L) | reference(Microsoft Learn)
6. 付録：参照一覧（Microsoft Learn）、取得手順/コマンド（実行したもののみ）

## 6) 仕上げ
- 途中経過のファイル乱立は避け、最終成果物は上記レポートに集約する。
- ただし `{WORK}` は「根拠・棚卸し・実行記録」として残す（後続のSubや再実行のため）。

## 7) 受入観点（完了条件の補足）

### 7.1 位置付け

以下のドメイン固有観点は成果物の受入条件であり、出力前に行う別の検証ステップでも、敵対的レビューの発動条件でもない。

### 7.2 ドメイン固有観点
- **レビュー完全性・妥当性**：すべてのリソースが棚卸しされているか、Well-Architected Framework の5本柱がすべてカバーされているか、Azure Security Benchmark v3 に基づく指摘は網羅的か、各推奨の根拠（Microsoft Learn参照）は正確か、複数案が必要な場合に提示されているか
- **ユーザー/利用者視点**：レポートが実装チーム・セキュリティチームにわかりやすいか、Mermaid 図は直感的で正確か、棚卸し表の情報粒度は適切か、指摘の優先度（Critical/High/Medium/Low）は正当か、次アクション・推奨が実行可能か
- **保守性・再現性・拡張性**：レビュー手順が再現可能か、新しいリソース追加時の更新方法が明確か、中間成果物（{WORK} の notes・inventory）の記録は十分か、参照リンク（Microsoft Learn）の正確性・最新性、権限不足・取得不可範囲の明記の有無

### 7.3 反映方法
観点を満たさない箇所は作業中に主成果物で直し、独立したレビュー成果物は作らない。完了報告の検証結果には結果を簡潔に含める。
