<!-- subissue -->
<!-- title: [AAD] Step.1.1: ドメイン分析 -->
<!-- labels: aad:ready, copilot -->
<!-- custom_agent: Arch-Microservice-DomainAnalytics -->

## 目的

ユースケース文書を根拠に、DDD 観点でドメイン分析を実施する。

## 完了条件

- [ ] docs/domain-analytics.md が作成されている
- [ ] Bounded Context が定義されている

---

<!-- subissue -->
<!-- title: [AAD] Step.1.2: サービス一覧抽出 -->
<!-- labels: aad:ready, copilot -->
<!-- custom_agent: Arch-Microservice-ServiceIdentify -->
<!-- depends_on: 1 -->

## 目的

ドメイン分析結果からマイクロサービス候補を抽出する。

## 完了条件

- [ ] docs/service-list.md が作成されている
- [ ] サービス境界が定義されている

---

<!-- subissue -->
<!-- title: [AAD] Step.2: データモデリング -->
<!-- labels: aad:ready, copilot -->
<!-- custom_agent: Arch-DataModeling -->
<!-- depends_on: 1,2 -->

## 目的

全エンティティを抽出し、データモデルを設計する。

## 完了条件

- [ ] docs/data-model.md が作成されている
- [ ] ER 図（Mermaid）が含まれている
