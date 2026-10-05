---
name: microservice-design-guide
description: >
  マイクロサービスの設計ガイドを提供する。サービス定義・API 設計・ 境界コンテキストとの対応・デプロイ単位の決定手順を定義する。 USE FOR: microservice design, service definition, API design. DO NOT USE FOR: microservice implementation. WHEN: マイクロサービスを設計する、サービス定義書を作成する。
metadata:
  origin: user
  version: 1.0.0
---

# microservice-design-guide

## 目的

マイクロサービス設計書（SVC-*.md）の作成ガイドとテンプレートを提供する。

## Non-goals（このスキルの範囲外）

- **マイクロサービスの実装** — Dev-Microservice-Azure-ServiceCoding 等の Agent が担当
- **データフロー処理設計** — Skill `dataflow-design-guide` が担当
- **デプロイ** — Dev-Microservice-Azure-ComputeDeploy 等の Agent が担当

## ガイド一覧（references/）

| ファイル | 内容 |
|---------|------|
| `references/microservice-definition.md` | マイクロサービス定義書テンプレ（サービスメタ情報・API・イベント・データ・セキュリティ） |

## 使用方法

`Arch-Microservice-ServiceDetail` など Microservice 系 Agent は
`references/microservice-definition.md` を参照してサービス定義書を作成する。

## 成果物パス

サービスごとの成果物: `docs/usecase/<usecaseId>/services/<serviceId>-<serviceNameSlug>-description.md`

## 注意事項

- 推測は禁止。根拠がない場合は `TBD` を置き、根拠のパスを記す
- `docs/**/SVC-*.md, docs/services/**` に applyTo で適用される

## Related Skills

| Skill | 関係 | 説明 |
|-------|------|------|
| `dataflow-design-guide` | 代替 | データフロー処理設計が必要な場合 |
| `work-artifacts-layout` | 出力先 | サービス定義書の docs/usecase/... 配下への保存先 |
| `task-dag-planning` | 先行 | マイクロサービス設計作業の計画 |
| `architecture-questionnaire` | 先行 | アーキテクチャ選定後にサービス設計へ遷移 |
