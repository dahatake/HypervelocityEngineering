{root_ref}
## 目的
ユースケース文書を根拠に、DDD観点でドメイン分析を行い、docs/catalog/domain-analytics.md を作成する。
本ステップは Web アプリ・データフローアプリ・AI Agent の全アプリ種別を対象とし、APP-ID 横断の単一の真実源（Single Source of Truth）となる。

## バッチ/データフロー補強観点
ユースケース文書または `docs/catalog/app-catalog.md` からデータフロー型アプリ（バッチ・ストリーミング）を含むことが確認できるドメインについてのみ、以下を分析に含めること。不明な項目は推測せず `TBD` または `不明（要確認）` と明記する。
- 冪等性キー（Idempotency Key）と再実行時の整合性
- トランザクション境界と最終的一貫性（Eventually Consistent）の許容範囲
- チェックポイント/リスタート方針
- リトライ・補償トランザクション・デッドレターの取扱
- データ品質（欠損・重複・遅延データ）の境界条件

該当観点は、ドメイン分析の既存見出し（集約・ドメインイベント・メモ等）に、ユースケース根拠付きで反映すること。

## 前提条件
- `docs/catalog/app-catalog.md` が存在すること（App Architecture Design の成果物）

## 入力
- `docs/catalog/use-case-catalog.md`
- `docs/catalog/app-catalog.md`（アプリケーション一覧）

## 出力
- `docs/catalog/domain-analytics.md`

{existing_artifact_policy}

## Custom Agent
`Arch-Microservice-DomainAnalytics` を使用

## 依存
- Step.1（ソフトウェアアーキテクチャの推薦）が `aas:done` であること

## 完了条件
- `docs/catalog/domain-analytics.md` が作成されている
{completion_instruction}{additional_section}
