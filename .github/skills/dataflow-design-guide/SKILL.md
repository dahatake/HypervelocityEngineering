---
name: dataflow-design-guide
description: >
  HVE ADFD/ADFDV 生成時のデータフロー成果物契約エントリ。要件定義・ジョブ定義・データフロー・ 非機能要件・ワークフロー仕様・テスト仕様・テスト戦略を references/ に集約し、 SKILL.md 本文から索引を提供する。 USE FOR: HVE ADFD/ADFDV generation contract, dataflow artifact contract lookup. DO NOT USE FOR: generic batch tutorial, batch implementation. WHEN: HVE ADFD/ADFDV のデータフロー成果物を生成・確認するとき。
metadata:
  origin: user
  version: 1.0.0
---

# dataflow-design-guide

## 目的

HVE ADFD/ADFDV 生成で使用するデータフロー成果物契約の入口として、必要なガイド・テンプレートへの索引を一元管理する。

## ガイド一覧（references/）

| ファイル | 内容 |
|---------|------|
| `references/dataflow-requirements.md` | データフロー処理要件定義書テンプレ（バッチ候補一覧・トリガー・データソース・SLA） |
| `references/dataflow-data-flow.md` | データフロー定義書テンプレ（ソース→変換→シンク・Mermaid図） |
| `references/dataflow-job-design.md` | ジョブ設計書テンプレ（ジョブ一覧・DAG・スケジューリング・リトライ・冪等性） |
| `references/dataflow-job-definition.md` | データフローアプリ定義書テンプレ（入力スキーマ・変換ロジック・出力スキーマ・エラー処理） |
| `references/dataflow-non-functional.md` | 非機能要件設計書テンプレ（監視・オブザーバビリティ・スケーリング・セキュリティ） |
| `references/dataflow-workflow-spec.md` | パイプラインオーケストレーション仕様テンプレ（スケジューリング・外部連携・構成管理） |
| `references/dataflow-test-strategy.md` | データフローテスト戦略書テンプレ（テストピラミッド・テストデータ・テストダブル・データ品質） |
| `references/dataflow-test-spec.md` | データフローテスト仕様書テンプレ（テストケース一覧・テストデータ仕様・テストダブル設計） |

## 使用方法

各 Batch 系 Agent は該当するテンプレートを参照して成果物を作成する。
全テンプレートは `applyTo: "docs/**/batch-*.md, src/**/batch/**"` で適用される。

## Related Skills

| Skill | 関係 | 説明 |
|-------|------|------|
| `microservice-design-guide` | 代替 | リアルタイム API 設計が必要な場合は microservice-design-guide を使用する |
| `work-artifacts-layout` | 出力先 | データフロー設計書の work/ 配下への保存先 |
| `task-dag-planning` | 先行 | データフロー設計作業の計画・DAG 作成に使用する |
