---
name: test-strategy-template
description: >
  テスト戦略の共通テンプレート。テストピラミッド定義・テストダブル選択基準・
  テストデータ戦略・カバレッジ方針を提供する。
  USE FOR: test strategy, test pyramid, test doubles selection,
  Azurite, Testcontainers, WireMock, test data strategy,
  Faker, seed management, coverage policy.
  DO NOT USE FOR: test code generation (agents do that),
  individual test case design (Arch-TDD-TestSpec Agent が担当),
  CI/CD pipeline integration (use github-actions-cicd).
  WHEN: テスト戦略書を作成する、テストダブルの選択基準を参照する、
  テストデータ戦略を定義する、カバレッジ方針を確認する。
metadata:
  origin: user
  version: "2.0.0"
---

# test-strategy-template

## 目的

テスト戦略書・テスト仕様書に共通する **テスト設計の原則** を一元管理する。各 Agent は本 Skill を参照し、固有のテスト種別のみを Agent 側に記載する。

---

## Non-goals

- **テストコードの生成** — Dev-*-TestCoding 系 Agent が担当
- **個別テストケースの設計** — Arch-TDD-TestSpec Agent が担当
- **CI/CD パイプラインへのテスト組み込み** — Skill `github-actions-cicd` または Dev-*-Deploy 系 Agent が担当

---

## 原則サマリー（詳細: `references/test-design-principles.md`）

- **テストピラミッド**: Unit Test 70-80% / Integration Test 15-20% / E2E Test 5-10%
- **テストダブル選択**: Azurite（Azure Storage）→ Testcontainers（DB/コンテナ）→ Mock/Stub（その他）の優先順位
- **テストデータ**: Faker（ランダム生成）/ シード管理（固定シード・再現可能）/ 本番データサニタイズ
- **カバレッジ**: Unit Test ビジネスロジック 80% 以上、変換ロジック 100% 目標

---

## ガイド一覧（references/）

| ファイル | 内容 |
|---------|------|
| `references/test-design-principles.md` | §1 テストピラミッド定義、§2 テストダブル選択基準（依存パターン別推奨ツール・優先順位）、§3 テストデータ戦略（Faker/シード管理/本番サニタイズ・エッジケース）、§4 カバレッジ方針 |

---

## 入出力例

> ※ 以下は説明用の架空例です

**例1（SVC-10 Azure Functions マイクロサービス）**: Unit Test(pytest + unittest.mock) 75% / Integration Test(pytest + Testcontainers + WireMock) 20% / E2E Test 5%

**例2（バッチ処理テストダブル設計）**: Azure Blob Storage → Azurite（優先順位1）/ Cosmos DB → Testcontainers（優先順位2）/ 外部REST API → WireMock（優先順位3）

## 参照元

- `work/Issue-skills-migration-investigation/duplication-patterns.md` — P-06 の詳細
