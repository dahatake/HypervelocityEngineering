---
name: github-actions-cicd
description: >
  GitHub Actions CI/CD ワークフローの共通仕様。OIDC 認証・workflow_dispatch トリガー・
  Copilot push 制約対応・シークレット管理・デプロイ保護の原則を提供する。
  USE FOR: GitHub Actions, CI/CD workflow, OIDC authentication,
  workflow_dispatch, copilot push workaround, deploy protection.
  DO NOT USE FOR: application code deployment
  (use appropriate azure-platform/ deployment skill),
  test execution (use harness-verification-loop),
  infrastructure provisioning (use azure-cli-deploy-scripts).
  WHEN: GitHub Actions ワークフローを作成する、CI/CD パイプラインを設計する、
  OIDC 認証を設定する、Copilot push 制約を回避する。
metadata:
  origin: user
  version: "2.0.0"
---

# github-actions-cicd

## 目的

GitHub Actions CI/CD ワークフローの **共通仕様** を一元管理する。各 Deploy Agent は本 Skill を参照し、ワークフロー固有の設定（デプロイ先・ビルドコマンド等）のみを Agent 側に記載する。

---

## 3原則（詳細: `references/cicd-common-spec.md`）

1. **OIDC 認証優先**: `azure/login@v2` + OIDC フェデレーション（secret-less）。`environment: copilot` 指定必須
2. **workflow_dispatch トリガー必須**: Copilot push 制約（自動発火しない）の回避。PR description に手動実行案内を記載する
3. **シークレット管理**: GitHub Secrets から取得。ハードコード禁止。ログ漏洩なし

---

## ガイド一覧（references/）

| ファイル | 内容 |
|---------|------|
| `references/cicd-common-spec.md` | §1 認証方式（OIDC推奨・YAML例・例外）、§2 Copilot push制約と workflow_dispatch（PR description手動実行案内テンプレート）、§3 ワークフロー共通仕様（トリガー・シークレット管理・デプロイ保護） |

---

## 入出力例

> ※ 以下は説明用の架空例です

**例1（Azure Functions デプロイ）**: `on: [push, pull_request, workflow_dispatch]` + `permissions: id-token:write` + `environment: copilot` + `azure/login@v2`

**例2（Copilot push 後の手動実行）**: PR description に「⚡ GitHub Actions Workflow の手動実行が必要です」案内を記載 → 「Approve and run workflows」ボタンをクリック

## 参照元

- `work/Issue-skills-migration-investigation/duplication-patterns.md` — P-04 の詳細
