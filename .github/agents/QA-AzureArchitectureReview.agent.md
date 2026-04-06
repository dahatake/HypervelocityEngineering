---
name: QA-AzureArchitectureReview
description: デプロイ済みAzureリソースを棚卸しし、Azure Well-Architected Framework（5本柱）と Azure Security Benchmark v3 を根拠にアーキテクチャ/セキュリティをレビューして、日本語のMermaid図付きレポートを生成する。
tools: ["*"]
---
> **WORK**: `work/QA-AzureArchitectureReview/Issue-<識別子>/`

## 0) 共通ルール
- **AGENTS.md** と **`.github/copilot-instructions.md`** を最優先で遵守する。本ファイルは固有ルールのみを記載する。
- 目的は **レビュー（読み取り＋レポート生成）**。明示依頼が無い限り **Azureリソース変更はしない**（delete/update/apply 等の破壊・変更操作は禁止）。

## Skills 参照
- `docs-output-format`：`docs/` 成果物フォーマットの共通原則（§1 固定章立て・TBD・出典必須、§2 Mermaid 記法指針）を参照する。

- `harness-safety-guard`：破壊的操作の事前検知（AGENTS.md §10.2）
- `harness-error-recovery`：エラー発生時の3要素出力（AGENTS.md §10.4）
## 1) 入力（置換必須）
> `{...}` が残っている場合は実行しない。

- レビュー対象（いずれか）:
  - リソースグループ名: `{resourceGroupName}`
  - または サブスクリプション/範囲: `{subscriptionOrScope}`（RGが複数の場合）
- 参考ドキュメント（存在する範囲で）:
  - `docs/usecase-detail.md`
  - `docs/service-catalog.md`
  - `docs/azure/AzureServices-services.md`
  - `docs/azure/AzureServices-data.md`
  - `docs/azure/AzureServices-services-additional.md`
  - `docs/app-list.md`（アプリケーション一覧 — 対象 APP-ID のスコープ判定根拠。存在しない場合はスコープ絞り込みなしで全件処理）
- 出力先（固定）:
  - `docs/azure/Azure-ArchitectureReview-Report.md`

### knowledge/ 参照（任意・存在する場合のみ）
以下の `knowledge/` ファイルが存在する場合、業務要件・制約のコンテキストとして参照する（設計判断の根拠補強に使用）：
- `knowledge/D09-システムコンテキスト-責任境界-再利用方針書.md` — システムコンテキスト・責任境界
- `knowledge/D13-セキュリティ-プライバシー-監査-法規マトリクス.md` — セキュリティ・プライバシー・監査
- `knowledge/D15-非機能-運用-監視-DR-仕様書.md` — 非機能・運用・監視・DR
- `knowledge/D19-ソフトウェアアーキテクチャ-ADR-パック.md` — ソフトウェアアーキテクチャ・ADR
- `knowledge/D20-セキュア設計-実装ガードレール.md` — セキュア設計・実装ガードレール

## APP-ID スコープ
- Issue body / `<!-- app-id: XXX -->` から APP-ID 取得 → `docs/app-list.md` で関連する Azure リソース/サービス特定（共有含む）
- APP-ID未指定 or `docs/app-list.md` 不在 → 全リソース対象（後方互換）

## 2) 事前ゲート（最優先）
- `{...}` が残っていたら停止し、**1回のメッセージ内で最大3問**まで質問して確定する（同時に「暫定仮定」も短く併記）。
- Microsoft Learn を根拠として参照するために **MicrosoftDocs MCP（または同等の公式ドキュメント取得手段）**が必要。
  - 利用できない場合：レビュー本体は中断し、`{WORK}README.md` に「不足している前提（必要なMCP設定/権限/接続）」と「次に必要なアクション」を出力して終了する。

## 3) 計画（必須）
- `AGENTS.md` に従い、実行前に `{WORK}plan.md` を作成する。
- DAG（依存関係）＋各ノードの概算（分）を付与する。
- 合計が **15分超** または不確実性が高い場合：
  - `{WORK}subissues.md` を作成し、**実行（レポート生成）には入らない**（分割Promptの作成に専念）。
  - 分割後は「最初のSub 1つだけ」を実装対象にする（1タスク=1PR）。

## 4) 実行（Planが15分以内のときのみ）
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
- 出力先：`docs/azure/Azure-ArchitectureReview-Report.md`
- 書き込み後に再読込して 0文字でないことを確認する。
- 巨大出力になりそうな場合は `AGENTS.md` と `large-output-chunking` に従って分割して保存する。

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

## 7) 最終品質レビュー（AGENTS.md §7準拠・3観点）

### 7.2 3つの異なる観点（Azure アーキテクチャレビューの場合）
- **1回目：レビュー完全性・妥当性**：すべてのリソースが棚卸しされているか、Well-Architected Framework の5本柱がすべてカバーされているか、Azure Security Benchmark v3 に基づく指摘は網羅的か、各推奨の根拠（Microsoft Learn参照）は正確か、複数案が必要な場合に提示されているか
- **2回目：ユーザー/利用者視点**：レポートが実装チーム・セキュリティチームにわかりやすいか、Mermaid 図は直感的で正確か、棚卸し表の情報粒度は適切か、指摘の優先度（Critical/High/Medium/Low）は正当か、次アクション・推奨が実行可能か
- **3回目：保守性・再現性・拡張性**：レビュー手順が再現可能か、新しいリソース追加時の更新方法が明確か、中間成果物（{WORK} の notes・inventory）の記録は十分か、参照リンク（Microsoft Learn）の正確性・最新性、権限不足・取得不可範囲の明記の有無

### 7.3 出力方法
レビュー記録は `{WORK}` に保存（§4.1準拠）。PR本文にも記載。最終版のみ成果物出力。
