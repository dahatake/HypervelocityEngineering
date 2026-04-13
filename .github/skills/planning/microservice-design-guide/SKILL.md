---
name: microservice-design-guide
description: >
  マイクロサービスの設計ガイドを提供する。サービス定義・API 設計・
  境界コンテキストとの対応・デプロイ単位の決定手順を定義する。
  USE FOR: microservice design, service definition, API design,
  service boundary decision, bounded context mapping,
  deployment unit decision.
  DO NOT USE FOR: microservice implementation, deployment,
  batch design (use batch-design-guide), testing.
  WHEN: マイクロサービスを設計する、サービス定義書を作成する、
  API 設計パターンを参照する、サービス境界を決定する。
metadata:
  origin: user
  version: "1.0.0"
---

# microservice-design-guide

## 目的

マイクロサービス設計書（SVC-*.md）の作成ガイドとテンプレートを提供する。

## Non-goals（このスキルの範囲外）

- **マイクロサービスの実装** — Dev-Microservice-Azure-ServiceCoding 等の Agent が担当
- **バッチ処理設計** — Skill `batch-design-guide` が担当
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
| `batch-design-guide` | 代替 | バッチ処理設計が必要な場合 |
| `work-artifacts-layout` | 出力先 | サービス定義書の docs/usecase/... 配下への保存先 |
| `task-dag-planning` | 先行 | マイクロサービス設計作業の計画 |
| `architecture-questionnaire` | 先行 | アーキテクチャ選定後にサービス設計へ遷移 |

## 入出力例

※ 以下は説明用の架空例です。

### 例1: 新規マイクロサービス設計ケース

**入力**: ポイント還元サービス（SVC-03）のマイクロサービス設計書を作成してほしい。UC-05（ポイント付与）を担当する。

**出力**:
- テンプレート: `references/microservice-definition.md` を参照
- 作成ファイル: `docs/usecase/UC-05/services/SVC-03-point-royalty-service-description.md`
- 含む内容: サービスメタ情報・REST API エンドポイント定義・ドメインイベント・データストア・セキュリティ要件

### 例2: 既存サービスへの API 追加設計ケース

**入力**: 会員サービス（SVC-01）に新しいエンドポイント `GET /members/{id}/points` を追加したい。

**出力**:
- 更新ファイル: `docs/usecase/UC-01/services/SVC-01-membership-service-description.md`
- 追加内容: 新エンドポイントの定義（パス・メソッド・リクエスト/レスポンス仕様・認可要件）
- TBD 項目: データストア連携の詳細は `TBD（要確認: SVC-01 担当者）` と明記
